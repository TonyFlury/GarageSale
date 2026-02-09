import io

import googleapiclient
from credentials import google_drive_info
from django.conf import settings
from google.api_core.exceptions import Forbidden
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from . import google_oauth
from ..models import DriveFile

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
]

class GoogleDrive:
    """
    Represents integration with the Google Drive API.

    This class provides utilities for authenticating, querying, and manipulating
    files and folders on Google Drive. It utilizes the Google API client library
    to interact with the Drive service. Common use cases include searching for
    files or folders by name, creating subfolders, managing folder hierarchies,
    and uploading files.

    Attributes:
        credentials: google_oauth.GoogleDriveCompanyCredential
            The credentials instance used for authenticating the Google Drive API.
        drive_service: googleapiclient.discovery.Resource
            A service instance for interacting with Google Drive via the API.
    """
    def __init__(self, credentials: google_oauth.GoogleDriveCompanyCredential = None ):
        self._credentials = credentials if credentials else google_oauth.get_or_create_company_credential()

        self._drive_service = self._build_company_drive_service(refresh_token=self._credentials.refresh_token)

    def _build_company_drive_service(self, refresh_token: str ):
        """
        Builds and returns a Google Drive service instance authenticated using the provided
        refresh token. This method uses the Google API client library to construct the service.

        Parameters:
        refresh_token (str): The refresh token to obtain a new access token for authenticating
            the Google Drive API service.

        Returns:
        googleapiclient.discovery.Resource: A Google Drive service object constructed with the
            provided credentials.
        """
        creds = Credentials(
            token=None,
            refresh_token=self._credentials.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=google_drive_info.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=google_drive_info.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=DRIVE_SCOPES,
        )
        return build("drive", "v3", credentials=creds)

    def find_file_by_name(self, file_name: str, parent: str = None) -> DriveFile|None:
        """
        Find a file by its name in a specific parent folder.

        This method searches for a file in the database with the specified name and parent folder.
        It returns the first matching result or None if no file is found. The file must have a non-null
        drive_file_id to be considered valid.

        Arguments:
            file_name (str): Name of the file to search for.
            parent (str, optional): ID of the parent folder to restrict the search within. Defaults to None.

        Returns:
            DriveFile: The first file matching the name and parent folder criteria, or None if no match is found.
        """
        # Use the Drive File model in preference to going to the Google drive API directly
        already_uploaded =DriveFile.objects.filter(name=file_name, drive_file_id__isnull=False, parent_folder_id=parent).first()
        if already_uploaded:
            return already_uploaded
        else:
            on_drive = self._drive_service.files().list(q=f"'{parent if parent else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID}' in parents and name='{file_name}'").execute()["files"]
            if on_drive:
                return on_drive[0]
            else:
                return None

    def find_folder_id_by_name(self, folder_name: str, parent: str = None):
        """
        Retrieves the ID of a folder on Google Drive by its name within a specified parent folder.

        This method queries Google Drive for a folder with the given name within the specified
        parent folder. If no parent folder is specified, it defaults to the root folder defined
        by the application settings. If multiple folders with the same name are found, an exception
        is raised.

        Parameters:
            folder_name (str): The name of the folder to search for.
            parent (str, optional): The ID of the parent folder to search within. Defaults to None.

        Returns:
            str | None: The ID of the folder if found, or None if no folder with the specified name exists.

        Raises:
            Exception: Raised if more than one folder is found with the same name.
        """
        folders = self._drive_service.files().list(q=f"'{parent if parent else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and name='{folder_name}'").execute()["files"]
        if len(folders) > 1:
            raise Exception(f"More than one folder found with name '{folder_name}'")
        return folders[0]["id"] if folders else None

    def create_sub_folder(self, parent: str, folder_name: str):
        """
        Creates a subfolder in a specified parent folder within Google Drive.

        This method leverages the Google Drive API to create a folder under a
        given parent folder. If no parent folder is specified, the root folder
        defined in the settings will be used as the default parent.

        Parameters:
        parent: str
            The ID of the parent folder where the subfolder will be created.
            If not provided, the default root folder ID will be used.

        folder_name: str
            The name of the folder to be created.

        Returns:
        str
            The ID of the newly created folder.
        """
        print('create_sub_folder', parent,repr(folder_name))
        folder_id = self._drive_service.files().create(body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder",
                                                   'parents':[parent if parent else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID]}).execute()["id"]
        return folder_id

    def get_or_create_sub_folder(self,folder_name: str, parent=None):
        """
        Retrieve the ID of a sub-folder by its name within a specified parent folder, or create a new sub-folder if it does not
        exist.

        Arguments:
        folder_name (str): The name of the sub-folder to be found or created.
        parent (optional): The ID of the parent folder where the sub-folder is searched or created. If not provided, the default
            parent is taken from the configuration.

        Returns:
        str: The ID of the sub-folder that was found or created.
        """
        return (self.find_folder_id_by_name(parent=google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID if not parent else parent,
                                            folder_name=folder_name) or
                    self.create_sub_folder(parent=google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID if not parent else parent,
                                           folder_name=folder_name))

    def get_or_create_path(self, path: str, root_folder: str=None, create_parents: bool = True):
        """
        Retrieves or creates a folder hierarchy in Google Drive based on a given path.

        This method processes the given path by splitting it into segments and traversing or creating
        the necessary folders. If `create_parents` is set to True, missing parent folders in the path
        will also be created. If `create_parents` is False, and a parent folder does not exist, a
        FileNotFoundError will be raised. This ensures the folder structure matches the provided path,
        starting from the specified root folder or the default root folder.

        Parameters:
        path: str
            The desired folder path in Google Drive to retrieve or create. It should be a string
            representation of the folder hierarchy separated by '/'.
        root_folder: str, optional
            The ID of the root folder under which the path hierarchy begins. If not provided,
            it defaults to `settings.GOOGLE_DRIVE_ROOT_FOLDER_ID`.
        create_parents: bool
            A flag indicating whether to create intermediate folders if they are missing. Defaults to True.

        Returns:
        str
            The ID of the final folder in the path hierarchy.

        Raises:
        FileNotFoundError
            If `create_parents` is False and any parent folder in the path does not exist.
        """
        segments = path.split("/")
        parent = root_folder if root_folder else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID
        folder_id = None
        for index, segment in enumerate(segments):
            if not segment:
                continue
            folder_id = self.find_folder_id_by_name(parent=parent, folder_name=segment)
            if folder_id is None:
                if not create_parents and index < len(segments) - 1:
                    raise FileNotFoundError(f"Cannot create '{path}' as folder '{'/'.join(segments[:index])}' does not exist")
                folder_id = self.create_sub_folder(parent=parent, folder_name=segment)
            print('get_or_create_path', parent,segment,folder_id)
            parent = folder_id
        return folder_id

    def move(self, source_file_id: str, dest_file_name: str, parent: str = None):
        self._drive_service.files().update(fileId=source_file_id, body={"name": dest_file_name, "parents":[parent if parent else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID]}).execute()

    def _upload_file(self, source_data, dest_file_name:str, folder_id: str | None=None,
                     content_type: str = "application/octet-stream",
                     make_backup=False) -> DriveFile:
        """
        Uploads a file to Google Drive using the provided data and metadata.

        This method uploads the given file data to Google Drive with the specified
        destination file name. It allows the file to be placed into a specified folder,
        or defaults to a predefined root folder if no folder ID is provided. The content
        type of the file can also be customized.

        Parameters:
            source_data: The file-like object containing the data to be uploaded.
            dest_file_name: str
                The name of the file to be created in Google Drive.
            folder_id: str or None, optional
                The ID of the folder where the file should be stored. If not provided,
                the default root folder ID from application settings is used.
            content_type: str, default "application/octet-stream"
                The MIME type of the file content.

        Returns:
            dict
                A dictionary containing information about the created file, including
                its ID, name, MIME type, size, and web view link.
        """
        print('uploading file', dest_file_name, folder_id)
        media = MediaIoBaseUpload(
            source_data,
            mimetype=content_type,
            resumable=True,
                )

        metadata: dict = {"name": dest_file_name,
                          "parents":[folder_id if folder_id else google_drive_info.GOOGLE_DRIVE_ROOT_FOLDER_ID]}

        existing_file = self.find_file_by_name(file_name=dest_file_name, parent=folder_id)
        if make_backup and existing_file:
            root, ext = dest_file_name.rsplit(".", 1)
            self.move(source_file_id=existing_file.drive_file_id,
                      dest_file_name=f"{root}_backup.{ext}",
                      parent=folder_id)

        created = self._drive_service.files().create( body=metadata, media_body=media,
                                                    fields="id,name,mimeType,size,webViewLink",
                                                    ).execute()

        entry = DriveFile.objects.create(
                drive_file_id=created["id"],
                parent_folder_id=folder_id,
                name=created.get("name", dest_file_name),
                mime_type=created.get("mimeType", content_type),
                size=created.get("size") or None,
                web_view_link=created.get("webViewLink", ""),
                )

        return entry

    def get_permission(self, file_id, permission_id=None):
        """
        Gets the permission or list of permissions for a specified file.

        If a specific permission ID is provided, retrieves the details of that
        permission for the given file ID. Otherwise, retrieves a list of all
        permissions associated with the file.

        Args:
            file_id (str): The ID of the file for which the permissions are
                being retrieved.
            permission_id (str, optional): The ID of a specific permission.
                Defaults to None.

        Returns:
            dict: A dictionary representation of the permission(s). If a
            specific permission ID is provided, the dictionary contains the
            details of that permission. Otherwise, it contains a list of
            permissions associated with the file.
        """
        return self._drive_service.permissions().list(fileId=file_id).execute() if permission_id else self._drive_service.permissions().get(fileId=file_id, permissionId=permission_id).execute()

    def set_permissions(self, file_id, role, type_="user", email=None):
        """
        Sets the permissions for a specific file on a Google Drive instance.

        This method uses the Google Drive API to modify the permissions for a file, such as assigning roles or defining the type of access.

        Arguments:
            file_id (str): The ID of the file on Google Drive whose permissions are to be modified.
            role (str): The role to be assigned to the file (e.g., "reader", "writer").
            type_ (str, optional): The type of permission assignee, typically "user" or "group". Default is "user".
            email (str, optional): The email address of the user or group to whom the permission should be granted.
        """
        self._drive_service.permissions().create(fileId=file_id, body={"role": role, "type": type_, "emailAddress": email}).execute()

    def upload_file(self, source_file, dest_file_name:str, file_path:str='',
                    folder_id: str | None=None, root_folder: str=None,
                    content_type: str = "application/octet-stream",
                    make_backup=False):
        """
        Uploads a file to a specified destination while handling optional folder hierarchy.

        This method uploads the provided source file to the destination folder in a storage system.
        If `file_path` is provided, it ensures the full path exists (creating folders as needed)
        and determines the folder ID. If `folder_id` is provided, it directly uploads to the
        specified folder. The file is uploaded with the specified MIME type, defaulting to
        'application/octet-stream'.

        Args:
            source_file: The local path to the file that needs to be uploaded.
            dest_file_name (str): The name to use for the file at the destination.
            file_path (str, optional): The file path in the remote hierarchy where the file
                should be uploaded. Either `file_path` or `folder_id` is required.
            folder_id (str | None, optional): The ID of the folder where the file should be
                uploaded. Default is None.
            root_folder (str, optional): The root folder ID in the hierarchy for resolving
                the path when `file_path` not provided. Default is None.
            content_type (str, optional): The MIME type of the file being uploaded. Default
                is 'application/octet-stream'.

        Raises:
            AttributeError: Raised if neither `file_path` nor `folder_id` is provided.
            Exception: Propagates exceptions that occur while seeking the file content
                during upload.

        Returns:
            None
        """
        if not folder_id:
            if file_path:
                folder_id = self.get_or_create_path(path=file_path, root_folder=root_folder)
            else:
                raise AttributeError("Either file_path or folder_id must be provided")

        if hasattr(source_file, "read"):
            file_data = source_file
            return self._upload_file(source_data=file_data, dest_file_name=dest_file_name,
                                     folder_id=folder_id, content_type=content_type,
                                     make_backup=make_backup)
        else:
            try:
               with open(source_file, "rb") as file_data:
                    file_data.seek(0)
            except Exception as e:
                    raise e from None
            else:
                return self._upload_file(source_data=file_data, dest_file_name=dest_file_name,
                                         folder_id=folder_id, content_type=content_type,
                                         make_backup=make_backup)


    def upload_django_uploaded_file(self, uploaded_file, folder_id: str | None,
                                    make_backup=False):
        """
        Uploads a Django uploaded file to a specified folder.

        Detailed Summary:
        This method processes a file uploaded through Django's file-handling framework and uploads it to
        a specific location, identified by a folder ID. It retrieves the file object from the uploaded file,
        ensures the file pointer is at the correct position, and delegates the upload operation to another
        function.

        Args:
            uploaded_file: The file object provided by Django's file-handling system. It must have
                           a `file` attribute and represent a valid uploaded file.
            folder_id: The identifier of the destination folder, where the file should be uploaded.
                       It can be provided as a string value or left as None if no specific folder
                       is targeted.

        Returns:
            The result of the upload operation from the `_upload_file` method. This is often a
            confirmation or metadata describing the successful upload process.
        """
        fileobj = uploaded_file.file
        try:
            fileobj.seek(0)
        except Exception:
            pass

        return self._upload_file(source_data=fileobj, dest_file_name=uploaded_file.name,
                                 folder_id=folder_id,
                                 content_type=getattr(uploaded_file, "content_type", "application/octet-stream"),
                                 make_backup=make_backup)

