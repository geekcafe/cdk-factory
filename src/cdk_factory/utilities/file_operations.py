"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import shutil
import inspect
import zipfile
from typing import List
from pathlib import Path

from aws_lambda_powertools import Logger


logger = Logger(__name__)


class ZipFile:
    def __init__(self) -> None:
        self.name: str | None = None
        self.file_path: str | None = None
        self.archive_path: str | None = None


class FileOperations:
    def __init__(self) -> None:
        pass

    @staticmethod
    def makedirs(path):
        abs_path = os.path.abspath(path)
        os.makedirs(abs_path, exist_ok=True)

    @staticmethod
    def clean_directory(path):
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            items = os.listdir(abs_path)
            for item in items:
                path = os.path.join(abs_path, item)
                if os.path.exists(path):
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        elif os.path.isfile(path):
                            os.remove(path)

                    except Exception as e:  # pylint: disable=W0718
                        logger.exception(f"clean up error {str(e)}")

    @staticmethod
    def get_directory_name(path: str):
        dirname = os.path.dirname(path)
        return dirname

    @staticmethod
    def write_file(path: str, output: str, append: bool = False) -> str:
        """
        Writes to a file
        Args:
            path (str): path
            output (str): text to write to the file
            append (bool): if true this operation will append to the file
                otherwise it will overwrite. the default is to overwrite
        Returns:
            str: path to the file
        """
        dirname = FileOperations.get_directory_name(path)
        FileOperations.makedirs(dirname)
        mode = "a" if append else "w"

        with open(path, mode=mode, encoding="utf-8") as file:
            file.write(output)

        return path

    @staticmethod
    def listdir(
        directory_path: str,
        include_full_path: bool = True,
        include_subdirectories: bool = True,
    ):
        files: List[str] = []

        if include_subdirectories:
            for root, _, filenames in os.walk(directory_path):
                for file in filenames:
                    file_path = os.path.join(root, file)
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(
                            "Attempting to list a directory.  The file returned cannot be found."
                        )
                    if include_full_path:
                        files.append(file_path)
                    else:
                        files.append(file)
        else:
            filenames = os.listdir(directory_path)

            if include_full_path:
                tmp = [os.path.join(directory_path, filename) for filename in filenames]
                files = tmp
            else:
                files = filenames

        return files

    @staticmethod
    def zip_directory(
        directory: str,
        zip_file_name: str | None = None,
        archive_root: str = "/",
        exclude_list: List[str] | None = None,
    ):
        if zip_file_name:
            zip_file_path = os.path.join(directory, zip_file_name)
        else:
            zip_file_path = f"{directory}.zip"
        files: List[ZipFile] = FileOperations.generate_zip_file_list(
            directory_path=directory,
            archive_root=archive_root,
            exclude_list=exclude_list,
        )

        FileOperations.write_to_zip_file(files, zip_file_path)

        return zip_file_path

    @staticmethod
    def write_to_zip_file(files: List[ZipFile], zip_file_path: str) -> str:
        """_summary_

        Args:
            files (List[str]): list of files to zip
            zip_file_path (_type_): path to the zip file

        Returns:
            str: path to zip file
        """

        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            for file in files:
                if file.file_path and os.path.exists(file.file_path):
                    logger.debug(
                        {
                            "source": "write_to_zip_file",
                            "file": f"f{file.file_path}",
                            "metric_filter": "write_to_zip_file",
                        }
                    )
                    if not file.file_path:
                        raise ValueError(
                            "File path cannot be empty.  Failed to write to zip file."
                        )
                    zipf.write(file.file_path, file.archive_path)
                else:
                    logger.debug(
                        {
                            "source": "write_to_zip_file",
                            "warning": f"file does not exist {file.file_path}",
                            "metric_filter": "write_to_zip_file_warning",
                        }
                    )

        return zip_file_path

    @staticmethod
    def get_file_extension(file_name, include_dot=False):
        logger.debug(f"getting extension for {file_name}")
        # get the last part of a string after a period .
        extension = os.path.splitext(file_name)[1]
        logger.debug(f"extension is {extension}")

        if not include_dot:
            if str(extension).startswith("."):
                extension = str(extension).removeprefix(".")
                logger.debug(f"extension after prefix removal: {extension}")

        return extension

    @staticmethod
    def get_file_name_from_path(path):
        logger.debug(f"getting file name from {path}")
        # get the last part of a string after a period .
        file_name = os.path.basename(path)

        return file_name

    @staticmethod
    def generate_zip_file_list(
        directory_path: str,
        archive_root: str | None = None,
        exclude_list: List[str] | None = None,
    ) -> List[ZipFile]:
        """
        Generates a zip file list.

        Args:
            directory_path (str): _description_
            archive_root (str | None, optional): _description_. Defaults to None.

        Raises:
            FileNotFoundError: _description_

        Returns:
            List[ZipFile]: _description_
        """

        files: List[ZipFile] = []

        for root, _, filenames in os.walk(directory_path):
            for file in filenames:
                file_path = os.path.join(root, file)
                if not os.path.exists(file_path):
                    raise FileNotFoundError(
                        "Attempting to list a directory.  The file returned cannot be found."
                    )
                zip_file: ZipFile | None = FileOperations.generate_zip_file_model(
                    file_path=file_path,
                    directory_path=directory_path,
                    archive_root=archive_root,
                )

                if isinstance(exclude_list, list) and zip_file and zip_file.file_path:
                    for exclude in exclude_list:
                        if exclude in zip_file.file_path:
                            zip_file = None
                            break
                if zip_file:
                    files.append(zip_file)

        return files

    @staticmethod
    def generate_zip_file_model(
        file_path: str,
        *,
        directory_path: str | None = None,
        archive_root: str | None = None,
    ) -> ZipFile:
        zip_file = ZipFile()
        zip_file.name = os.path.basename(file_path)
        zip_file.file_path = file_path

        if archive_root:
            if not directory_path:
                directory_path = str(Path(file_path).parent)

            # remove the directory path, and leave the file path along with
            # an archive root
            zip_file.archive_path = (
                f"{archive_root}{file_path.replace(str(directory_path), '')}"
            )
        else:
            zip_file.archive_path = file_path

        if str(zip_file.archive_path).startswith("//"):
            zip_file.archive_path = zip_file.archive_path.removeprefix("/")

        return zip_file

    @staticmethod
    def find_file(directories: List[str], file_name: str) -> str | None:
        for directory in directories:
            file_path = os.path.join(directory, file_name)
            if os.path.exists(file_path):
                return file_path

        return None

    @staticmethod
    def find_directory(directories: List[str], relative_directory: str) -> str | None:
        for directory in directories:
            sub_dir = os.path.join(directory, relative_directory)
            if os.path.exists(sub_dir):
                return sub_dir

        return None

    @staticmethod
    def caller_app_dir(default: str = ".") -> str:
        # frame[0] is this function; frame[1] is the factory; frame[2] should be app.py
        for frame_info in inspect.stack():
            # first non-package frame likely belongs to app.py
            candidate = os.path.abspath(os.path.dirname(frame_info.filename))
            if "site-packages" not in candidate and "dist-packages" not in candidate:
                return candidate
        return os.path.abspath(default)
