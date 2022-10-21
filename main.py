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
    # Connect to database
    conn = pymysql.connect(host='localhost',
                           user='root',
                           password='',
                           database='imagey')
    return conn


class Cache:

    def __init__(self):
        self.cache = OrderedDict()
        self.keys = []

        self.size = (1000) * 1024 * 1024

        # self.capacity = (1000) * 1024 * 1024
        self.used = 0

        self.hit_count = 0
        self.miss_count = 0
        self.replacment_policy = "LRU"
        self.number_of_items = 0
        self.number_of_requests_served = 0

        self.refreshConfiguration()
        self.scheduler()

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

            # Check if hash exists
            cursor = conn.cursor()
            sql = f"SELECT image FROM images WHERE hash='{key}'"
            numberOfHashes = cursor.execute(sql)

            if numberOfHashes == 0:
                # If hash does not exist return None
                return None
            else:
                row = cursor.fetchone()
                path = f"static/uploaded images/{row[0]}"

                image = self.put(key, path)

                if image != None:
                    return image["data"]
                else:
                    return None

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

    def setReplacment(self, policy: str) -> None:
        self.replacment_policy = policy

    def getCache(self, ):
        cache = {}
        for key in self.cache.keys():
            cache[key] = {
                'hash': key,
                'name': self.cache[key]['ImageName'],
                'size': "{0:.2f}".format(self.cache[key]['size'] / 1000 / 1000),
                'lastTimeUsed': self.cache[key]['LastTimeUsed'],
            }
        return cache

    def setSize(self, size: int) -> None:
        self.size = size * 1024 * 1024
        while self.used > self.size:
            self.replace()

    def getSize(self, ) -> int:
        return int(self.size) / 1024 / 1024

    def getUsedSpace(self, ) -> int:
        return self.used / 1024 / 1024

    def getFreeSpace(self, ) -> int:
        return (self.size - self.used) / 1024 / 1024

    def getNumberOfItems(self, ) -> int:
        return len(self.cache)

    def getReplacePolicy(self, ) -> int:
        return self.replacment_policy

    def scheduler(self, ):
        # Push statistics every 5 sec
        threading.Timer(5.0, self.storeStatistics).start()

    def storeStatistics(self, ) -> None:
        if self.hit_count > 0 or self.miss_count > 0 or self.number_of_items != len(
                self.cache):
            # Connect to database
            conn = connection()

            cursor = conn.cursor()
            sql = f"INSERT INTO `statistics`(`hit`, `miss`, `number_of_items`, `total_size`, `number_of_requests_served`) VALUES ('{self.hit_count}','{self.miss_count}','{len(self.cache)}','{self.getUsedSpace()}','{self.number_of_requests_served}')"
            cursor.execute(sql)

            # Commit changes
            conn.commit()

            # Close connection
            conn.close()

            # Clear old values
            self.hit_count = 0
            self.miss_count = 0
            self.number_of_items = len(self.cache)
            self.number_of_requests_served = 0

        self.scheduler()

    def clear(slef, ):
        slef.cache.clear()
        # slef.capacity = slef.size
        slef.used = 0

    def state(self, ):
        print(f"Number of items: {self.getNumberOfItems()}")
        print(f"Size: {self.size / 1024 / 1024}")
        # print(f"Capacity: {self.capacity / 1024 / 1024}")
        print(f"Used: {self.used / 1024 / 1024}")
        print(
            "============================================================================================================================"
        )

    def refreshConfiguration(self, ):
        # Connect to database
        conn = connection()

        cursor = conn.cursor()

        count = cursor.execute(
            f"SELECT size, replace_policy FROM `cache` WHERE created_at = (SELECT MAX(created_at) FROM cache)")

        if count != 0:
            row = cursor.fetchone()
            self.setSize(row[0])
            self.replacment_policy = row[1]


# Cache
cache = Cache()

# Connection
conn = connection()


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html', status=200)


@app.route('/add', methods=['GET', 'POST'])
def store():
    if request.method == 'GET':
        # Show add page
        return render_template("add.html", status=200)

    if request.method == 'POST':
        # Connect to database
        conn = connection()

        # Get post request parameters
        hash = str(request.form["hash"])
        image = request.files['image']

        # Upload image
        file_name = f"{hash}_{image.filename}"
        image.save(f"static/uploaded images/{file_name}")

        # Check if hash exists
        cursor = conn.cursor()
        sql = f"SELECT image FROM images WHERE hash='{hash}'"
        numberOfHashes = cursor.execute(sql)

        if numberOfHashes == 0:
            # If hash does not exist insert to database
            sql = f"INSERT INTO images (hash, image) VALUES ('{hash}', '{file_name}')"
            cursor.execute(sql)
        else:
            #! Delete the old image form disk
            old_image = cursor.fetchone()[0]
            os.remove(f"static/uploaded images/{old_image}")

            # ? Update the image with the new one
            sql = f"UPDATE images SET image='{file_name}' WHERE hash='{hash}'"
            cursor.execute(sql)
            cache.put(hash, f"static/uploaded images/{file_name}")

        # Commit changes
        conn.commit()

        # Close connection
        conn.close()

        return render_template("add.html", status=201, added=True)

        # Redirect to show page
        return redirect(url_for("show"))


@app.route('/get', methods=['GET', 'POST'])
def show():
    if request.method == 'GET':
        # Show get page
        return render_template("get.html", status=200)

    if request.method == 'POST':
        # Get post request parameters
        hash = str(request.form["hash"])

        # Get the path FROM the cache
        image = cache.get(hash)

        if image == None:
            return render_template("get.html",
                                   hash=hash,
                                   message="Hash not found!",
                                   status=400)
        else:
            # Show get page
            return render_template("get.html",
                                   hash=hash,
                                   image=image,
                                   status=200)


@app.route('/keys', methods=['GET'])
def keys():
    # Connect to database
    conn = connection()

    # Create new cursor
    cursor = conn.cursor()

    # Get all keys
    numberOfKeys = cursor.execute("SELECT hash FROM images")

    # Close connection
    conn.close()

    if numberOfKeys > 0:
        # Show keys page
        return render_template("keys.html", keys=cursor, status=200)
    else:
        return render_template("keys.html", status=200)


@app.route('/control', methods=['GET', 'POST'])
def control():
    if request.method == 'GET':
        # Show control page
        return render_template("control.html", status=200, size=cache.getSize(), replace_policy=cache.getReplacePolicy())

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

        # Commit changes
        conn.commit()

        # Close connection
        conn.close()

        # Refresh
        cache.refreshConfiguration()

        return render_template("control.html", status=200, updated=True, size=cache.getSize(), replace_policy=cache.getReplacePolicy())


@app.route('/clear', methods=['POST'])
def clear():
    cache.clear()
    # return redirect(url_for("statistics", cleared=True))
    return render_template("control.html", status=200, cleared=True, size=cache.getSize(), replace_policy=cache.getReplacePolicy())


@app.route('/statistics', methods=['GET'])
def statistics(cleared=False, updated=False):
    current_statistics = {}
    statistics_past_10_min = {}
    statistics_all_times = {}

    # Connect to database
    conn = connection()
    cursor = conn.cursor()

    # ? Current statistics
    current_statistics["total_space"] = cache.getSize()
    current_statistics["free_space"] = cache.getFreeSpace()
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

    sql = "set @hits := 0;"
    cursor.execute(sql)
    sql = "set @misses := 0;"
    cursor.execute(sql)
    sql = "set @requests := 0;"
    cursor.execute(sql)
    sql = "select (@hits := @hits + hit) as hits, (@misses := @misses + miss) as misses, (@requests := @requests + number_of_requests_served), UNIX_TIMESTAMP(created_at) as requests from statistics order by created_at;"
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
    conn.close()

    # Show statistics page
    return render_template("statistics.html", current_statistics=current_statistics, statistics_past_10_min=statistics_past_10_min, statistics_all_times=statistics_all_times, status=200, cleared=cleared, times1=times1, hits=hits, misses=misses, requests=requests, times2=times2, sizes=sizes)


@app.route('/cache/keys', methods=['GET'])
def cacheKeys():
    c = cache.getCache()
    for key in c.keys():
        print(c[key]['hash'])
        print(c[key]['size'])
        print(c[key]['lastTimeUsed'])
        print(c[key]['name'])
    return render_template("cachekeys.html", status=200, keys=cache.getCache())


app.run(debug=True)
