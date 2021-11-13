#!/usr/bin/env python
# -*- coding:utf-8 -*-

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from os.path import join

from boto3.session import Session
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

_ = join


def upload_mod_to_s3(upload_file_path,
                     name,
                     bucket_name,
                     access_key,
                     secret_access_key,
                     region):
    """
    S3にファイルをアップロードする
    :param upload_file_path:
    :param name:
    :param bucket_name:
    :param access_key:
    :param secret_access_key:
    :param region:
    :return: CDNのURL
    """
    session = Session(aws_access_key_id=access_key,
                      aws_secret_access_key=secret_access_key,
                      region_name=region)

    s3 = session.resource('s3')
    s3.Bucket(bucket_name).upload_file(upload_file_path, name)

    return "{}/{}".format("https://d3fxmsw7mhzbqi.cloudfront.net", name)


def upload_mod_to_google_drive(upload_file_path,
                               name,
                               folder_id):
    """
    GoogleDriveにファイルをアップロードする
    :param upload_file_path:
    :param name:
    :param folder_id:
    :return: CDNのURL
    """

    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()

    # Create GoogleDrive instance with authenticated GoogleAuth instance.
    drive = GoogleDrive(gauth)

    file1 = drive.CreateFile({
        'title': name,
        'parents': [
            {
                "kind": "drive#fileLink",
                "id": folder_id
            }
        ]
    })
    file1.SetContentFile(upload_file_path)
    file1.Upload()

    file1.InsertPermission({
        'type': 'anyone',
        'value': 'anyone',
        'role': 'reader'})

    file1.FetchMetadata()

    return "{}/{}?key={}&alt=media".format("https://www.googleapis.com/drive/v3/files",
                                           file1['id'],
                                           "AIzaSyAAt1kNBcu9uiPWPIxAcR0gZefmWHcjjpM")


def download_asset_from_github(repository_author,
                               repository_name,
                               out_file_path,
                               release_tag=None,
                               file_name=None):
    """
    githubからアセットをダウンロード。未指定の場合は最新を取得
    :param repository_author:
    :param repository_name:
    :param release_tag:
    :param file_name:
    :param out_file_path:
    :return:
    """
    api_base_url = "https://api.github.com/repos/{}/{}".format(repository_author, repository_name)

    if release_tag is None:
        response = urllib.request.urlopen("{}/releases/latest".format(api_base_url))
        content = json.loads(response.read().decode('utf8'))
        release_tag = content["tag_name"]

    if file_name is None:
        response = urllib.request.urlopen("{}/releases/tags/{}".format(api_base_url, release_tag))
        content = json.loads(response.read().decode('utf8'))
        file_name = content["assets"][0]["name"]

    request_url = "{}/{}/{}/releases/download/{}/{}".format("https://github.com",
                                                            repository_author,
                                                            repository_name,
                                                            release_tag,
                                                            file_name
                                                            )
    req = urllib.request.Request(request_url)

    with open(out_file_path, "wb") as my_file:
        my_file.write(urllib.request.urlopen(req).read())

    return out_file_path


def assembly_core_mod_zip_file(resource_font_asset_zip_file_path,
                               resource_image_file_path,
                               resource_interface_dir_path,
                               out_file_path):
    """
    コアモッドを作成
    :param resource_font_asset_zip_file_path:　githubにあるフォントアセットのzipファイルのパス
    :param resource_image_file_path: 画像ファイルパス
    :param resource_interface_dir_path: インターフェースディレクトリパス
    :param out_file_path: 出力ファイルパス
    :return:
    """

    with tempfile.TemporaryDirectory() as temp_dir_path:
        # 画像ファイル
        shutil.copy(resource_image_file_path, temp_dir_path)

        # interface
        shutil.copytree(resource_interface_dir_path, _(temp_dir_path, "interface"))

        # gfx
        salvage_files_from_github_font_zip(out_dir_path=_(temp_dir_path, "gfx", "fonts"),
                                           filter_f_f=lambda x: True,
                                           resource_path=resource_font_asset_zip_file_path)

        # zip化する
        return shutil.make_archive(out_file_path, 'zip', root_dir=temp_dir_path)


def salvage_files_from_github_font_zip(out_dir_path,
                                       filter_f_f,
                                       resource_path):
    with zipfile.ZipFile(resource_path) as font_zip:
        special_files = filter(filter_f_f, font_zip.namelist())

        font_zip.extractall(path=out_dir_path, members=special_files)


def generate_dot_mod_file(mod_title_name,
                          mod_file_name,
                          mod_tags,
                          mod_image_file_path,
                          mod_supported_version,
                          out_dir_path):
    """
    .modファイルを作る
    :param mod_title_name:
    :param mod_file_name: zipファイルの名前（.zipを含まない）
    :param mod_tags: Set<String>型
    :param mod_image_file_path:
    :param mod_supported_version:
    :param out_dir_path: 出力ディレクトリのパス
    :return: 出力ファイルパス
    """

    os.makedirs(out_dir_path, exist_ok=True)

    out_file_path = _(out_dir_path, "{}.mod".format(mod_file_name))

    with open(out_file_path, "w", encoding="utf-8") as fw:
        lines = [
            'name="{}"'.format(mod_title_name),
            'archive="mod/{}.zip"'.format(mod_file_name),
            'tags={}'.format("{" + " ".join(map(lambda c: '"{}"'.format(c), mod_tags)) + "}"),
            'picture="{}"'.format(mod_image_file_path),
            'supported_version="{}"'.format(mod_supported_version)
        ]

        fw.write("\n".join(lines))

    return out_file_path


def generate_distribution_file(url,
                               mod_file_path,
                               out_file_path):
    """
    trielaで使用する配布用設定ファイルを作成する。
    :param url:
    :param mod_file_path:
    :param out_file_path:
    :return:
    """

    with open(mod_file_path, 'rb') as fr:
        md5 = hashlib.md5(fr.read()).hexdigest()

    d_new = {'file_md5': md5,
             'url': url,
             'file_size': os.path.getsize(mod_file_path)}

    with open(out_file_path, "w", encoding="utf-8") as fw:
        json.dump(d_new, fw, indent=2, ensure_ascii=False)


def pack_mod(out_file_path,
             mod_zip_path,
             mod_title_name,
             mod_file_name,
             mod_tags,
             mod_image_file_path,
             mod_supported_version):
    with tempfile.TemporaryDirectory() as temp_dir_path:
        # .modファイルを作成する
        generate_dot_mod_file(
            mod_title_name=mod_title_name,
            mod_file_name=mod_file_name,
            mod_tags=mod_tags,
            mod_image_file_path=mod_image_file_path,
            mod_supported_version=mod_supported_version,
            out_dir_path=temp_dir_path)

        # zipをコピー
        shutil.copy(mod_zip_path, _(temp_dir_path, "{}.zip".format(mod_file_name)))

        return shutil.make_archive(out_file_path, 'zip', root_dir=temp_dir_path)


def main():
    # 一時フォルダ用意
    os.makedirs(_(".", "tmp"), exist_ok=True)
    os.makedirs(_(".", "out"), exist_ok=True)

    # フォントセットの最新版をダウンロードする
    font_file_path = download_asset_from_github(repository_author="matanki-saito",
                                                repository_name="EU4fontcreate",
                                                out_file_path=_(".", "tmp", "font.zip"))

    print("font_file_path:{}".format(font_file_path))

    # コアModを構築する
    core_mod_zip_file_path = assembly_core_mod_zip_file(
        resource_font_asset_zip_file_path=font_file_path,
        resource_image_file_path=_(".", "resource", "title.jpg"),
        resource_interface_dir_path=_(".", "resource", "interface"),
        out_file_path=_(".", "tmp", "mod"))

    print("core_mod_zip_file_path:{}".format(core_mod_zip_file_path))

    # packする
    mod_pack_file_path = pack_mod(
        out_file_path=_(".", "out", "eu4_ap0_mod"),
        mod_file_name="jpmod_ap0_mod",
        mod_zip_path=core_mod_zip_file_path,
        mod_title_name="JPMOD Main 1: Fonts and UI",
        mod_tags={"Translation", "Localisation"},
        mod_supported_version="1.32.*.*",
        mod_image_file_path="title.jpg")

    print("mod_pack_file_path:{}".format(mod_pack_file_path))

    if os.environ.get("FILE_REPOSITORY") == 'S3':
        # S3にアップロード from datetime import datetime as dt
        from datetime import datetime as dt
        cdn_url = upload_mod_to_s3(
            upload_file_path=mod_pack_file_path,
            name=dt.now().strftime('%Y-%m-%d_%H-%M-%S-{}.zip'.format("eu4-core")),
            bucket_name="triela-file",
            access_key=os.environ.get("AWS_S3_ACCESS_KEY"),
            secret_access_key=os.environ.get("AWS_S3_SECRET_ACCESS_KEY"),
            region="ap-northeast-1")
    else:
        # GoogleDriveにアップロード from datetime import datetime as dt
        from datetime import datetime as dt
        cdn_url = upload_mod_to_google_drive(
            upload_file_path=mod_pack_file_path,
            name=dt.now().strftime('%Y-%m-%d_%H-%M-%S-{}.zip'.format("eu4-core")),
            folder_id='1MUdH6S6O-M_Y5jRUzNrzQ8tPZOhm_aES')

    print("::set-output name=download_url::{}".format(cdn_url))

    # distributionファイルを生成する
    generate_distribution_file(url=cdn_url,
                               out_file_path=_(".", "out", "dist.v2.json"),
                               mod_file_path=mod_pack_file_path)


if __name__ == "__main__":
    main()
