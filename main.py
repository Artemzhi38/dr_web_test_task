import hashlib
import os

import redis
from dotenv import load_dotenv
from flask import Flask, make_response, render_template, request, send_file
from flask_httpauth import HTTPBasicAuth
from flask_restful import Api, Resource

load_dotenv()
auth = HTTPBasicAuth()
author_storage = redis.Redis(host="redis", port=6379, decode_responses=True)
app = Flask(__name__)
app.config["ALLOWED_EXTENSIONS"] = {"txt", "pdf", "png", "jpg", "jpeg", "gif"}
app.config["USER_DATA"] = {
    os.getenv("USER_ONE"): os.getenv("PASSWORD_ONE"),
    os.getenv("USER_TWO"): os.getenv("PASSWORD_TWO"),
}
app.config["DEBUG"] = os.getenv("DEBUG")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "store")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
api = Api(app)


def allowed_file(filename):
    """Функция проверки расширения файла"""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


@auth.verify_password
def verify(username, password):
    """Функция верификации пароля"""
    if not (username and password):
        return False
    return app.config["USER_DATA"].get(username) == password


class EndpointViewFiles(Resource):
    """Эндпоинт для отображения состояния файлового хранилища.
    Не требует авторизации"""

    def get(self):
        dirnames = os.listdir(app.config["UPLOAD_FOLDER"])
        filenames = []
        for dirname in dirnames:
            dir_filenames = os.listdir(
                os.path.join(app.config["UPLOAD_FOLDER"], dirname)
            )
            filenames.extend(
                [
                    (dirname, filename, author_storage.get(filename))
                    for filename in dir_filenames
                ]
            )
        return make_response(
            render_template("files.html", amount=len(filenames), filenames=filenames)
        )


class EndpointUpload(Resource):
    """Эндпоинт для загрузки файлов в файловое хранилище. Использование
    требует авторизации. Возвращает хэш содержимого файла по алгоритму md5,
    сам же файл получает в хранилище имя соответствующее этому хэшу и хранится
     в директории с названием равным первым двум буквам хэша."""

    @auth.login_required
    def post(self):
        if "file" not in request.files:
            return "No file"
        file = request.files["file"]
        if file.filename == "":
            return "Empty filename"
        if file and allowed_file(file.filename):
            hash_obj = hashlib.md5(file.stream.read())
            file_hash = hash_obj.hexdigest()
            dir_path = os.path.join(app.config["UPLOAD_FOLDER"], file_hash[:2])
            file_path = os.path.join(dir_path, file_hash)
            if not os.path.exists(dir_path):
                os.mkdir(dir_path)
            file.seek(0)
            file.save(file_path)
            author_storage.set(file_hash, str(auth.current_user()))
            return file_hash


class EndpointDelete(Resource):
    """Эндпоинт для удаления файлов из файлового хранилища. Использование
    требует авторизации. Принимает хэш файла полученный по алгоритму md5 и
    проверяет соответствие автора файла из хранилища текущему авторизованному
    пользователю. Удалить файл может только пользователь, создавший его.
    Информация об авторстве каждого из файлов в хранилище хранится в Redis."""

    @auth.login_required
    def delete(self, file_hash):
        dir_path = os.path.join(app.config["UPLOAD_FOLDER"], file_hash[:2])
        file_path = os.path.join(dir_path, file_hash)
        if os.path.exists(file_path):
            author = author_storage.get(file_hash)
            if author == str(auth.current_user()):
                os.remove(file_path)
                os.rmdir(dir_path)
                return f"{file_path} - deleted successfully!"
            return "Wrong author!"
        return "File does not exist!"


class EndpointDownload(Resource):
    """Эндпоинт для скачивания файлов из файлового хранилища. Не требует
    авторизации. Принимает хэш необходимого файла, полученный по алгоритму
    md5."""

    def get(self, file_hash):
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_hash[:2], file_hash)
        if not os.path.exists(file_path):
            return "File does not exist!"
        return send_file(file_path, download_name=file_hash, as_attachment=True)


api.add_resource(EndpointViewFiles, "/")
api.add_resource(EndpointUpload, "/upload")
api.add_resource(EndpointDownload, "/download/<file_hash>")
api.add_resource(EndpointDelete, "/delete/<file_hash>")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=app.config["DEBUG"])
