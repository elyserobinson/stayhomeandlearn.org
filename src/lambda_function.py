import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

import boto3
import gspread
import jinja2
from oauth2client.service_account import ServiceAccountCredentials

ROOT_DIR = Path(__file__).parent
TEMPLATE_DIR = ROOT_DIR / "template"
CSS_DIR = TEMPLATE_DIR / "css"
SITE_DIR = ROOT_DIR / "site"
DATA_DIR = ROOT_DIR / "data"

IGNORED_FILES = ["template.html", ".DS_Store"]

LISTS_MAPPING = {
    "learning_resources": "&#128218; Learning Resources",
    "productivity": "&#128187; Productivity",
    "health": "&#x1F3CB; Health & Fitness",
    "entertainment": "&#x1F4FA; Entertainment",
}

CONTENT_TYPE_MAPPING = {
    ".css": "text/css",
    ".html": "text/html",
    ".jpg": "image/jpeg",
    ".xml": "text/xml",
}

INTRO_TEXT = """
<b>COVID-19 continues disrupting lives.</b> Some are going through severe health situations. Others have lost their jobs. And by now, many of us are quarantined in our homes.
<br><br>
Life may feel tough now, but don't despair. This can be a time to learn new things, get better at your craft or enjoy (virtual) time with friends and family. 
<br><br>
<b>This page is a list of high-quality resources available for free or cheaper than usual due to the COVID-19:</b>
<a href="#learning_resources"> Learning Resources</a>,
<a href="#health"> Health & Fitness</a>,
<a href="#productivity"> Productivity</a>, and
<a href="#entertainment"> Entertainment</a>.
<br><br>
If you like them, use them or share them with others. If you know of something that is not here, <a href="https://docs.google.com/forms/d/e/1FAIpQLSf6qLcvJGWS3VltKV99sO0KhBxmWxb0sdIpVu93OolL42s7rQ/viewform?usp=sf_link">please let me know</a>.
"""
META_CONTENT = """
A list of +50 high-quality resources available for free or cheaper than usual due to the COVID-19
"""


def download_sheets():
    """Download sheets using the Google Sheets API"""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir()

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )
    client = gspread.authorize(credentials)

    workbook = client.open("Stay Home and Learn")
    for worksheet in workbook.worksheets():
        filename = DATA_DIR / (worksheet.title + ".csv")
        sheet_values = worksheet.get_all_values()
        print(f"Downloading: {worksheet.title}")
        with open(filename, "w") as f:
            writer = csv.writer(f)
            writer.writerows(sheet_values)


def generate_site():
    """Generate site in local directory"""
    shutil.rmtree(SITE_DIR, ignore_errors=True)
    SITE_DIR.mkdir()

    for filename in TEMPLATE_DIR.iterdir():
        if filename.is_dir():
            shutil.copytree(str(filename), SITE_DIR / filename.name)
        elif filename.name != "template.html" and filename.name != ".DS_Store":
            shutil.copy(str(filename), SITE_DIR)
    template_loader = jinja2.FileSystemLoader(searchpath=TEMPLATE_DIR)
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template("template.html")

    csv_files = [
        filename for filename in DATA_DIR.iterdir() if filename.suffix == ".csv"
    ]
    csv_files.sort()
    lists_all = []
    for csv_file in csv_files:
        original_name = re.search(r"[0-9]_(.*?)\.csv", csv_file.name).group(1)
        processed_name = LISTS_MAPPING.get(original_name, original_name)
        with open(str(csv_file), mode="r") as csv_file:
            csv_reader = csv.DictReader(csv_file)
            list_ind = [row for row in csv_reader]
            lists_all.append((original_name, processed_name, list_ind))

    curr_date = datetime.now().strftime("%B %-d, %Y")
    output = template.render(
        lists=lists_all,
        intro_text=INTRO_TEXT,
        last_update=curr_date,
        meta_content=META_CONTENT,
    )

    with open(SITE_DIR / "index.html", "w") as f:
        f.write(output)


def upload_recursively_to_s3(dir, s3, prefix=""):
    """Upload a directory to s3 in a recursive manner (adding all files under it)

    Parameters
    ----------
    dir: Directory to upload to S3
    s3: Boto3 S3 Resource
    prefix: Prefix for directory to upload (e.g. /css)
    """
    for filename in dir.iterdir():
        if filename.is_dir():
            upload_recursively_to_s3(filename, s3, prefix + filename.name + "/")
        elif filename.name not in IGNORED_FILES:
            content_type = CONTENT_TYPE_MAPPING.get(
                filename.suffix, "application/octet-stream"
            )
            s3.Bucket("dev-stayhomeandlearn.org").upload_file(
                Filename=str(filename),
                Key=prefix + filename.name,
                ExtraArgs={"ContentType": content_type},
            )


def build_site():
    download_sheets()
    generate_site()
    session = boto3.Session(profile_name="personal")
    s3 = session.resource("s3")
    upload_recursively_to_s3(dir=SITE_DIR, s3=s3)


if __name__ == "__main__":
    build_site()
