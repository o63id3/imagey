import base64
import datetime
import io
import os
import random
import threading
from collections import OrderedDict

import pymysql
from flask import Flask, redirect, render_template, request, url_for
from PIL import Image

app = Flask(__name__)


def connection():
    conn = pymysql.connect(host='localhost',
                           user='root',
                           password='',
                           database='imagey',
                           autocommit=True)
    return conn


class Cache:

    # Cache init
    def __init__(self):
        self.cache = OrderedDict()
        self.keys = []

        self.size = (1) * 1024 * 1024
        self.used = 0
        self.hit_count = 0
        self.miss_count = 0
        self.replacment_policy = "LRU"
        self.number_of_items = 0
        self.number_of_requests_served = 0

        self.refreshConfiguration()
        self.scheduler()

    # Get image from cache
    def get(self, key: str):
        self.number_of_requests_served = self.number_of_requests_served + 1

        # If key exists in cache
        if key in self.cache:
            self.hit_count = self.hit_count + 1
            self.cache.move_to_end(key)
            self.cache[key]["LastTimeUsed"] = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")
            return self.cache[key]["data"]
        else:
            self.miss_count = self.miss_count + 1

            # Connect to database
            conn = connection()

            cursor = conn.cursor()
            sql = f"SELECT image FROM images WHERE hash='{key}'"
            numberOfHashes = cursor.execute(sql)

            if numberOfHashes != 0:
                row = cursor.fetchone()
                path = f"static/uploaded images/{row[0]}"
                image = self.put(key, path)

                cursor.close()
                conn.close()

                return image["data"]

            cursor.close()
            conn.close()

            return None

    # Put image into cache
    def put(self, key: str, path: str):
        if os.path.exists(path):
            fileSize = os.path.getsize(path)

            im = Image.open(path)

            data = io.BytesIO()
            im.save(data, "JPEG")
            value = {
                "data": base64.b64encode(data.getvalue()).decode('utf-8'),
                "size": fileSize,
                "LastTimeUsed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ImageName": os.path.basename(path)
            }

            # Get image size in Bytes
            fileSize = value["size"]

            if fileSize > self.size:
                return value

            if key in self.cache:
                self.invalidateKey(key)

            while self.used + fileSize > self.size:
                self.replace()

            self.cache[key] = value
            self.used = self.used + fileSize
            self.keys.append(key)
            return value
        else:
            return None

    # Replace image from cache
    def replace(self, ) -> None:
        if len(self.cache) > 0:
            # LRU
            if self.replacment_policy == "LRU":
                item = self.cache.popitem(last=False)
                fileSize = item[1]["size"]

                self.used = self.used - fileSize
            # Random
            else:
                # Get random key
                key = random.choice(self.keys)

                # Delete the item
                self.invalidateKey(key)

    # Delete image from cache
    def invalidateKey(self, key: str) -> None:
        if key in self.cache:
            # Get file size in Bytes
            fileSize = self.cache[key]["size"]

            # Free space
            self.used = self.used - fileSize

            # Delete item FROM cache
            self.cache.pop(key)

            # Delete key
            self.keys.remove(key)

    # Refresh cache configuration
    def refreshConfiguration(self, ):
        # Connect to database
        conn = connection()

        cursor = conn.cursor()

        count = cursor.execute(
            "SELECT size, replace_policy FROM cache WHERE created_at = (SELECT MAX(created_at) FROM cache)")

        if count != 0:
            row = cursor.fetchone()
            self.setSize(row[0])
            self.replacment_policy = row[1]
        else:
            count = cursor.execute(
                f"INSERT INTO cache(size, replace_policy) VALUES ({self.getSize()},'{self.replacment_policy}')")

        cursor.close()
        conn.close()

    # Scheduler to store statistics every 5 sec
    def scheduler(self, ):
        # Push statistics every 5 sec
        threading.Timer(5.0, self.storeStatistics).start()

    # Store statistics to database
    def storeStatistics(self, ) -> None:
        if self.hit_count > 0 or self.miss_count > 0 or self.number_of_items != len(
                self.cache):
            # Connect to database
            conn = connection()

            cursor = conn.cursor()
            sql = f"INSERT INTO `statistics`(`hit`, `miss`, `number_of_items`, `total_size`, `number_of_requests_served`) VALUES ('{self.hit_count}','{self.miss_count}','{len(self.cache)}','{self.getUsedSpace()}','{self.number_of_requests_served}')"
            cursor.execute(sql)

            # Close connection
            cursor.close()
            conn.close()

            # Clear old values
            self.hit_count = 0
            self.miss_count = 0
            self.number_of_items = len(self.cache)
            self.number_of_requests_served = 0

        self.scheduler()

    # Clear cache
    def clear(slef, ):
        slef.cache.clear()
        slef.used = 0

    # Get cache images without image itself
    def getCache(self, ):
        cache = {}
        for key in self.cache.keys():
            cache[key] = {
                'hash': key,
                'name': self.cache[key]['ImageName'],
                'size': "{0:.2f}".format(self.cache[key]['size'] / 1024 / 1024),
                'lastTimeUsed': self.cache[key]['LastTimeUsed'],
            }        
        return cache

    # Sets cache replacment policy
    def setReplacment(self, policy: str) -> None:
        self.replacment_policy = policy

    # Returns cache replacment policy
    def getReplacePolicy(self, ) -> str:
        return self.replacment_policy

    # Sets cache size
    def setSize(self, size: int) -> None:
        self.size = size * 1024 * 1024
        while self.used > self.size:
            self.replace()

    # Returns cache size
    def getSize(self, ) -> int:
        return int(self.size) / 1024 / 1024

    # Returns cache used space in MB
    def getUsedSpace(self, ) -> int:
        return self.used / 1024 / 1024

    # Returns cache free space in MB
    def getFreeSpace(self, ) -> int:
        return (self.size - self.used) / 1024 / 1024

    # Returns number of images inside cache
    def getNumberOfItems(self, ) -> int:
        return len(self.cache)


# Cache
cache = Cache()


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html'), 200


@app.route('/add', methods=['GET', 'POST'])
def store():
    if request.method == 'GET':
        return render_template("add.html"), 200

    if request.method == 'POST':
        # Connect to database
        conn = connection()

        # Get post request parameters
        hash = str(request.form["hash"])
        image = request.files["image"]

        # Upload image
        file_name = f"{hash}_{image.filename}"
        image.save(f"static/uploaded images/{file_name}")

        cursor = conn.cursor()
        sql = f"SELECT image FROM images WHERE hash='{hash}'"
        numberOfHashes = cursor.execute(sql)

        fileSize = os.path.getsize(f"static/uploaded images/{file_name}")

        if numberOfHashes == 0:
            # If hash does not exist insert to database
            sql = f"INSERT INTO images (hash, image, size) VALUES ('{hash}', '{file_name}', '{fileSize}')"
            cursor.execute(sql)
        else:
            # If hash do exist delete old image and update with new one
            old_image = cursor.fetchone()[0]
            os.remove(f"static/uploaded images/{old_image}")

            # ? Update the image with the new one
            sql = f"UPDATE images SET image='{file_name}', size='{fileSize}' WHERE hash='{hash}'"
            cursor.execute(sql)
            cache.put(hash, f"static/uploaded images/{file_name}")

        # Close connection
        cursor.close()
        conn.close()

        return render_template("add.html", added=True), 201


@app.route('/get', methods=['GET', 'POST'])
def show():
    if request.method == 'GET':
        return render_template("get.html"), 200

    if request.method == 'POST':
        # Get post request parameters
        hash = str(request.form["hash"])

        # Get the path FROM the cache
        image = cache.get(hash)

        if image == None:
            return render_template("get.html",
                                   hash=hash,
                                   message="Hash not found!"), 404
        else:
            # Show get page
            return render_template("get.html",
                                   hash=hash,
                                   image=image), 200


@app.route('/keys', methods=['GET'])
def keys():
    # Connect to database
    conn = connection()

    # Create new cursor
    cursor = conn.cursor()

    # Get all keys
    numberOfKeys = cursor.execute("SELECT hash, image, (size / 1024 / 1024), UNIX_TIMESTAMP(created_at), UNIX_TIMESTAMP(updated_at) FROM images")

    # Close connection
    cursor.close()
    conn.close()

    if numberOfKeys > 0:
        return render_template("keys.html", keys=cursor), 200
    else:
        return render_template("keys.html"), 200


@app.route('/control', methods=['GET', 'POST'])
def control():
    if request.method == 'GET':
        return render_template("control.html", size=cache.getSize(), replace_policy=cache.getReplacePolicy()), 200

    if request.method == 'POST':
        # Get post request parameters
        cache_size = (request.form["cache-size"])
        if int(request.form["replace-policy"]) == 0:
            replacement = "LRU"
        else:
            replacement = "RANDOM"

        # Connect to database
        conn = connection()

        # Create new cursor
        cursor = conn.cursor()

        cursor.execute(
            f"INSERT INTO `cache`(`size`, `replace_policy`) VALUES ('{cache_size}','{replacement}')"
        )

        # Close connection
        cursor.close()
        conn.close()

        # Refresh
        cache.refreshConfiguration()

        return render_template("control.html", updated=True, size=cache.getSize(), replace_policy=cache.getReplacePolicy()), 200


@app.route('/clear', methods=['POST'])
def clear():
    cache.clear()
    return render_template("control.html", cleared=True, size=cache.getSize(), replace_policy=cache.getReplacePolicy()), 200


@app.route('/statistics', methods=['GET'])
def statistics():
    current_statistics = {}
    statistics_past_10_min = {}
    statistics_all_times = {}

    # Connect to database
    conn = connection()
    cursor = conn.cursor()

    # ? Current statistics
    current_statistics["total_space"] = "{0:.2f}".format(cache.getSize())
    current_statistics["free_space"] = "{0:.2f}".format(cache.getFreeSpace())
    current_statistics["number_of_items"] = cache.getNumberOfItems()
    current_statistics["replace_policy"] = cache.getReplacePolicy()

    # ? Statistics past 10 min
    sql = "SELECT NVL(SUM(hit), 0), NVL(SUM(miss), 0) FROM statistics WHERE created_at >= date_sub(now(), interval 10 minute)"
    cursor.execute(sql)

    row = cursor.fetchone()

    if row[0] == 0 and row[1] == 0:
        statistics_past_10_min["hit_rate"] = "?"
        statistics_past_10_min["miss_rate"] = "?"
    else:
        statistics_past_10_min["hit_rate"] = round(
            (row[0] / (row[0] + row[1])) * 100, 2)
        statistics_past_10_min["miss_rate"] = "{0:.2f}".format(
            100 - statistics_past_10_min["hit_rate"])

    sql = "SELECT NVL(SUM(number_of_requests_served), 0) FROM statistics WHERE created_at >= date_sub(now(), interval 10 minute)"
    cursor.execute(sql)
    statistics_past_10_min["number_of_requests"] = cursor.fetchone()[0]

    # ? Statistics all times
    sql = "SELECT NVL(SUM(hit), 0), NVL(SUM(miss), 0) FROM statistics"
    cursor.execute(sql)

    row = cursor.fetchone()

    if row[0] == 0 and row[1] == 0:
        statistics_all_times["hit_rate"] = "?"
        statistics_all_times["miss_rate"] = "?"
    else:
        statistics_all_times["hit_rate"] = round(
            (row[0] / (row[0] + row[1])) * 100, 2)
        statistics_all_times["miss_rate"] = "{0:.2f}".format(
            100 - statistics_all_times["hit_rate"])

    sql = "SELECT NVL(SUM(number_of_requests_served), 0) FROM statistics"
    cursor.execute(sql)
    statistics_all_times["number_of_requests"] = cursor.fetchone()[0]

    # ? Plots
    times1 = []

    hits = []
    misses = []
    requests = []

    times2 = []
    sizes = []

    sql = "SET @hits := 0;"
    cursor.execute(sql)
    sql = "SET @misses := 0;"
    cursor.execute(sql)
    sql = "SET @requests := 0;"
    cursor.execute(sql)
    sql = "SELECT (@hits := @hits + hit) AS hits, (@misses := @misses + miss) AS misses, (@requests := @requests + number_of_requests_served), UNIX_TIMESTAMP(created_at) AS requests FROM statistics ORDER BY created_at;"
    count = cursor.execute(sql)

    if count > 0:
        rows = cursor.fetchall()

        for row in rows:
            hits.append(int(row[0]))
            misses.append(int(row[1]))
            requests.append(int(row[2]))
            times1.append(int(row[3]))

        sql = "SELECT size, UNIX_TIMESTAMP(created_at) FROM cache ORDER BY created_at"
        cursor.execute(sql)
        rows = cursor.fetchall()

        for row in rows:
            sizes.append(int(row[0]))
            times2.append(row[1])

        min_time = min(min(times1), min(times2))

        if min_time == min(times1):
            times2.insert(0, min_time)
            sizes.insert(0, sizes[0])
        # else:
        #     times1.insert(0, min_time)
        #     hits.insert(0, hits[0])
        #     misses.insert(0, misses[0])
        #     requests.insert(0, requests[0])


        for i in range(0, len(times1)):
            times1[i] -= min_time
            times1[i] /= 4000

        for i in range(0, len(times2)):
            times2[i] -= min_time
            times2[i] /= 4000

        max_time = max(max(times1), max(times2))

        if max_time == max(times1):
            times2.append(max_time)
            sizes.append(sizes[len(sizes) - 1])
        else:
            times1.append(max_time)
            hits.append(hits[len(hits) - 1])
            misses.append(misses[len(misses) - 1])
            requests.append(requests[len(requests) - 1])

    # Close connection
    cursor.close()
    conn.close()

    # Show statistics page
    return render_template("statistics.html",
                           current_statistics=current_statistics,
                           statistics_past_10_min=statistics_past_10_min,
                           statistics_all_times=statistics_all_times,
                           times1=times1,
                           hits=hits,
                           misses=misses,
                           requests=requests,
                           times2=times2,
                           sizes=sizes), 200


@app.route('/cache/keys', methods=['GET'])
def cacheKeys():
    return render_template("cachekeys.html",  keys=cache.getCache()), 200


app.run(debug=True)
