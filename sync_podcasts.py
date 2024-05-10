#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p mp3splt -p ffmpeg -p "python3.withPackages (p: [p.lxml p.requests p.tqdm p.python-slugify])"
import argparse
import calendar
from pathlib import Path
import tempfile
from subprocess import check_call
import requests
from lxml import etree
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import time
from slugify import slugify

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--media-dir", type=Path, required=True)
  parser.add_argument("--feed", type=str, required=True)

  args = parser.parse_args()

  last_sync_file = Path("last-sync")

  if not args.media_dir.is_dir():
    raise RuntimeError("Player not mounted.")

  feed_resp = requests.get(args.feed)
  feed_resp.raise_for_status()

  feed = etree.fromstring(feed_resp.content)

  last_sync = None
  if last_sync_file.exists():
    last_sync = time.gmtime(int(last_sync_file.read_text()))

  def process_item(item):
    title = item.find("title").text
    pub_date = time.strptime(item.find("pubDate").text, "%a, %d %b %Y %H:%M:%S %z")
    subtitle = item.find("itunes:subtitle", namespaces=feed.nsmap).text
    audio_url = item.find("enclosure").get("url")

    item_title = f"{subtitle} - {title}"

    if last_sync is not None and pub_date < last_sync:
      print(f"Skipping '{item_title}'")
      return

    out_dir = args.media_dir / slugify(item_title, max_length=255) # ensure directory name is okay on FAT32
    print(f"Writing to {out_dir}")

    with tempfile.TemporaryDirectory() as tmp_dir:
      normalized_file = Path(tmp_dir) / "normalized.mp3"

      check_call([
        "ffmpeg",
        "-i", audio_url,
        "-filter:a", "speechnorm=e=6.25:r=0.00001:l=1",
        "-b:a", "192k",
        str(normalized_file),
      ])

      check_call([
        "mp3splt",
        str(normalized_file),
        "-t", "5.0",
        "-a",
        "-d", str(out_dir),
      ])

  items = feed.xpath("//item")

  with ThreadPoolExecutor() as executor:
    list(tqdm(executor.map(process_item, items), unit="item", total=len(items), desc="Downloading items"))

  last_sync_file.write_text(str(calendar.timegm(time.gmtime())))

if __name__ == "__main__":
  main()
