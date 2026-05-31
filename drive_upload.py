import io
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google_auth import get_user_credentials

DEFAULT_FOLDER_ID = "1We1WUYqriSpew672xGV-CBkFZK5CgIEB"


def upload_excel_and_convert(
    excel_source,
    filename="habbit_tracker.xlsx",
    folder_id=None,
    file_id=None,
):
    """
    Upload .xlsx to Google Drive and convert to Google Sheet.

    If file_id is set, replace that existing Sheet (same URL every run).
    Otherwise create a new Sheet in folder_id.
    """
    creds = get_user_credentials()
    drive = build("drive", "v3", credentials=creds)

    if hasattr(excel_source, "read"):
        data = excel_source.read()
    else:
        data = excel_source.getvalue()

    media = MediaIoBaseUpload(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=False,
    )

    if file_id:
        file = drive.files().update(
            fileId=file_id,
            body={"mimeType": "application/vnd.google-apps.spreadsheet"},
            media_body=media,
            fields="id, webViewLink",
        ).execute()
    else:
        file_metadata = {
            "name": filename,
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        if folder_id:
            file_metadata["parents"] = [folder_id]

        file = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

    return file["webViewLink"]


if __name__ == "__main__":
    import sys

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    path = sys.argv[1] if len(sys.argv) > 1 else "habbit_tracker.xlsx"
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", DEFAULT_FOLDER_ID)
    file_id = os.getenv("GOOGLE_DRIVE_FILE_ID")
    filename = os.path.basename(path)

    with open(path, "rb") as f:
        link = upload_excel_and_convert(
            f, filename, folder_id=folder_id, file_id=file_id
        )

    if file_id:
        print(f"Updated existing sheet: {link}")
    else:
        print(f"Uploaded and converted (new file): {link}")
