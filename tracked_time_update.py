import requests
from datetime import datetime
import os

from database import (
    backup_table_to_csv,
    connect_db,
    create_tables_if_not_exists,
    insert_entries_to_db,
)
from folder_config import map_folder_name_from_task

CLICKUP_TOKEN = os.getenv("CLICKUP_API_KEY")
if not CLICKUP_TOKEN:
    raise ValueError("Missing required env var: CLICKUP_API_KEY")
TEAM_ID = os.getenv("CLICKUP_TEAM_ID")
if not TEAM_ID:
    raise ValueError("Missing required env var: CLICKUP_TEAM_ID")
HEADERS = {"Authorization": CLICKUP_TOKEN, "Content-Type": "application/json"}


def get_spaces(team_id):
    url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("spaces", [])


def get_folders(space_id):
    url = f"https://api.clickup.com/api/v2/space/{space_id}/folder"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("folders", [])


def get_lists(folder_id):
    url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("lists", [])


def get_lists_in_space(space_id):
    url = f"https://api.clickup.com/api/v2/space/{space_id}/list"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json().get("lists", [])


def get_tasks_from_list(list_id, due_date_gt=None, due_date_lt=None):
    tasks = []
    page = 0
    while True:
        url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
        params = {
            "page": page,
            "order_by": "created",
            "reverse": False,
            "include_closed": "true",
        }
        if due_date_gt is not None:
            params["due_date_gt"] = due_date_gt
        if due_date_lt is not None:
            params["due_date_lt"] = due_date_lt

        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("tasks", [])
        if not batch:
            break
        tasks.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return tasks


def ms_to_hm(ms):
    total_minutes = ms // (1000 * 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}:{minutes:02d}"


def main(range_start: datetime, range_end: datetime):
    """
    For tasks in the date range with start+due set, compute duration = due - start
    and upsert into Postgres (clickup_mkiel). Does not use ClickUp Time Tracking API
    (paid / rate-limited); your reports read from the local DB.
    """
    range_start_ms = int(range_start.timestamp() * 1000)
    range_end_ms = int(range_end.timestamp() * 1000)
    print("[INFO] Fetching all spaces...")
    spaces = get_spaces(TEAM_ID)

    all_tasks = []
    for space in spaces:
        space_id = space["id"]
        print(f"[INFO] Processing space: {space['name']} ({space_id})")

        folders = get_folders(space_id)
        lists = get_lists_in_space(space_id)

        for folder in folders:
            folder_lists = get_lists(folder["id"])
            lists.extend(folder_lists)

        print(f"[INFO] Found {len(lists)} lists in space {space['name']}")

        for lst in lists:
            list_id = lst["id"]
            print(f"[INFO] Fetching tasks from list: {lst['name']} ({list_id})")
            tasks = get_tasks_from_list(
                list_id, due_date_gt=range_start_ms, due_date_lt=range_end_ms
            )
            all_tasks.extend(tasks)

    print(f"[INFO] Total tasks fetched: {len(all_tasks)}")

    entries = []
    for task in all_tasks:
        task_id = task["id"]
        task_name = task.get("name", "<No Name>")

        created_date = task.get("date_created")
        if created_date is None:
            continue
        if isinstance(created_date, str):
            try:
                created_date = int(created_date)
            except ValueError:
                print(
                    f"[WARN] Task '{task_name}' (ID: {task_id}) has invalid created_date: {created_date}"
                )
                continue

        if not (range_start_ms <= created_date <= range_end_ms):
            continue

        start_date = task.get("start_date")
        due_date = task.get("due_date")

        if start_date is None or due_date is None:
            print(
                f"[WARN] Task '{task_name}' (ID: {task_id}) missing start or due date"
            )
            continue

        for field_name, field_value in [
            ("start_date", start_date),
            ("due_date", due_date),
        ]:
            if isinstance(field_value, str):
                if field_value.isdigit():
                    try:
                        field_value = int(field_value)
                    except ValueError:
                        field_value = None
                else:
                    field_value = None
            elif not isinstance(field_value, int):
                field_value = None

            if field_name == "start_date":
                start_date = field_value
            else:
                due_date = field_value

        if start_date is None or due_date is None:
            print(
                f"[WARN] Task '{task_name}' (ID: {task_id}) has invalid start or due date"
            )
            continue

        diff_ms = due_date - start_date
        diff_hours = diff_ms / (1000 * 60 * 60)

        if not (0 < diff_hours <= 24):
            print(
                f"[INFO] Task '{task_name}' (ID: {task_id}) duration {diff_hours:.2f}h not in (0,24] hours, skipping."
            )
            continue

        task_start_date = datetime.fromtimestamp(start_date / 1000).date()
        folder_name = map_folder_name_from_task(task)
        entries.append(
            {
                "task_id": str(task_id),
                "folder_name": folder_name,
                "task_start_date": task_start_date,
                "duration": diff_ms,
            }
        )
        start_dt = datetime.fromtimestamp(start_date / 1000)
        due_dt = datetime.fromtimestamp(due_date / 1000)
        print(
            f"[DB] Task: '{task_name}' (ID: {task_id}) | Start: {start_dt} | Due: {due_dt} | Duration: {ms_to_hm(diff_ms)}"
        )

    if not entries:
        print("[INFO] No rows to upsert.")
        return

    conn = connect_db()
    try:
        create_tables_if_not_exists(conn)
        backup_table_to_csv(conn, "clickup_mkiel")
        insert_entries_to_db(conn, entries)
    finally:
        conn.close()
    print(f"[INFO] Upserted {len(entries)} row(s) into clickup_mkiel.")


def _parse_cli_dates():
    import argparse
    from datetime import date, timedelta

    parser = argparse.ArgumentParser(
        description="Range sync: ClickUp tasks (by due date) → Postgres clickup_mkiel"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=int(os.getenv("SYNC_DAYS_BACK", "2")),
        help="Sync from (today - N days) through today (default: SYNC_DAYS_BACK or 2)",
    )
    parser.add_argument("--start", help="Start date YYYY-MM-DD (overrides --days-back)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = (
            datetime.strptime(args.end, "%Y-%m-%d").date()
            if args.end
            else date.today()
        )
    else:
        end = date.today() if not args.end else datetime.strptime(args.end, "%Y-%m-%d").date()
        start = end - timedelta(days=args.days_back)

    if start > end:
        parser.error("start date must be on or before end date")

    return (
        datetime.combine(start, datetime.min.time()),
        datetime.combine(end, datetime.max.time()),
    )


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    range_start, range_end = _parse_cli_dates()
    print(f"[INFO] Range sync {range_start.date()} → {range_end.date()}")
    main(range_start, range_end)
