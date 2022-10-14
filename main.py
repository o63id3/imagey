from dataclasses import replace
import os
import random
import threading
import time

import pymysql
from flask import Flask, redirect, render_template, request, url_for

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
        self.cache = dict()
        self.capacity = (1000) * 1024 * 1024
        self.size = (1000) * 1024 * 1024
        self.hit_count = 0
        self.miss_count = 0
        self.replacment_policy = 0
        self.number_of_items = 0

        # Connect to database
        conn = connection()

        cursor = conn.cursor()
        sql = f"SELECT count(*) FROM `cache`"
        cursor.execute(sql)

        if cursor.fetchone()[0] != 0:
            sql = f"SELECT size, replace_policy FROM `cache` where created_at = (SELECT MAX(created_at) FROM cache)"
            cursor.execute(sql)

            row = cursor.fetchone()

            self.capacity = row[0] * 1024 * 1024
            self.size = row[0] * 1024 * 1024
            if row[1] == "LRU":
                self.replacment_policy = 0
            else:
                self.replacment_policy = 1

        # Push statistics every 5 sec
        threading.Timer(5.0, self.storeStatistics).start()

    def get(self, key: str) -> str:
        # If key exists in cache
        if key in self.cache:
            self.hit_count = self.hit_count + 1
            self.cache[key]["LastTimeUsed"] = int(time.time() * 1000)
            return self.cache[key]["path"]
        else:
            self.miss_count = self.miss_count + 1

            # Connect to database
            conn = connection()

            # Check if hash exists
            cursor = conn.cursor()
            sql = f"SELECT count(*) FROM `images` WHERE hash='{key}'"
            cursor.execute(sql)

            if cursor.fetchone()[0] == 0:
                # If hash does not exist return empty string
                return ""
            else:
                sql = f"select hash, image from images where hash='{key}'"
                cursor.execute(sql)

                row = cursor.fetchone()

                hash = row[0]
                path = f"/static/uploaded images/{row[1]}"

                self.put(hash, path)

                return path

    def put(self, key: str, value: str) -> None:
        if key not in self.cache:
            # If image exists
            if os.path.exists(value):
                # Get image size in Bytes
                fileSize = os.path.getsize(value)

                # If cache has no free space replace
                if self.capacity - fileSize < 0:
                    self.replace()

                self.cache[key] = {
                    "path": value,
                    "LastTimeUsed": int(time.time() * 1000)
                }
                self.capacity = self.capacity - fileSize

    def replace(self, ) -> None:
        if len(self.cache) > 0:
            # LRU
            if self.replacment_policy == 0:
                key = min(self.cache.keys(),
                          key=(lambda k: self.cache[k]["LastTimeUsed"]))

                # Delete the item
                self.delete(key)
            # Random
            else:
                # Get random key
                key = random.choice(list(self.cache.keys()))

                # Delete the item
                self.delete(key)

    def delete(self, key: str) -> None:
        if key in self.cache:
            # Get file size in Bytes
            fileSize = os.path.getsize(self.cache[key]["path"])

            # Free space
            self.capacity = self.capacity + fileSize

            # Delete item from cache
            self.cache.pop(key)

    def setReplacment(self, policy: int) -> None:
        if 0 <= policy <= 1:
            self.replacment_policy = policy

    def setSize(self, size: int) -> None:
        size = size * 1024 * 1024

        self.capacity = self.capacity - self.size + size

        self.size = size

        while self.capacity < 0:
            self.replace()

    def getSize(self, ) -> int:
        return int(self.size) / 1024 / 1024

    def getFullSpace(self, ) -> int:
        return (self.size - self.capacity) / 1024 / 1024

    def getFreeSpace(self, ) -> int:
        return (self.size - self.getFullSpace()) / 1024 / 1024

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
            sql = f"INSERT INTO `statistics`(`hit`, `miss`, `number_of_items`, `free_space`) VALUES ('{self.hit_count}','{self.miss_count}','{len(self.cache)}','{self.getFreeSpace}')"
            cursor.execute(sql)

            # Commit changes
            conn.commit()

            # Close connection
            conn.close()

            # Clear old values
            self.hit_count = 0
            self.miss_count = 0
            self.number_of_items = len(self.cache)

        self.scheduler()

    def clear(slef, ):
        slef.cache.clear()
        slef.capacity = slef.size

    def state(self, ):
        print(f"Number of items: {self.getNumberOfItems()}")
        print(f"Size: {self.size}")
        print(f"Capacity: {self.capacity}")
        print(f"Hit: {self.hit_count}")
        print(f"Miss: {self.miss_count}")
        print(
            "============================================================================================================================"
        )


# Cache
cache = Cache()


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/add', methods=['GET', 'POST'])
def store():
    if request.method == 'GET':
        # Show add page
        return render_template("add.html")

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
        sql = f"SELECT count(*) FROM `images` WHERE hash='{hash}'"
        cursor.execute(sql)

        if cursor.fetchone()[0] == 0:
            # If hash does not exist insert to database
            sql = f"INSERT INTO images (hash, image) VALUES ('{hash}', '{file_name}')"
        else:
            #! Delete the old image form disk
            sql = f"select image from images where hash='{hash}'"
            cursor.execute(sql)
            old_image = cursor.fetchone()[0]
            os.remove(f"static/uploaded images/{old_image}")

            #? Update the image with the new one
            sql = f"UPDATE images SET image='{file_name}' WHERE hash='{hash}'"
        cursor.execute(sql)

        # Commit changes
        conn.commit()

        # Close connection
        conn.close()

        # Redirect to show page
        return redirect(url_for("show"))


@app.route('/get', methods=['GET', 'POST'])
def show():
    if request.method == 'GET':
        # Show get page
        return render_template("get.html")

    if request.method == 'POST':
        # Get post request parameters
        hash = str(request.form["hash"])

        # Get the path from the cache
        path = cache.get(hash)

        print(path)

        cache.state()
        if path == "":
            print("hi")
            return render_template("get.html",
                                   hash=hash,
                                   message="Hash not found!")
        else:
            # Show get page
            return render_template("get.html", hash=hash, image=path)


@app.route('/keys', methods=['GET'])
def keys():
    # Connect to database
    conn = connection()

    # Create new cursor
    cursor = conn.cursor()

    # Get all keys
    cursor.execute("SELECT hash FROM images")

    keys = []
    count = 1
    for row in cursor.fetchall():
        keys.append({"id": count, "hash": row[0]})
        count = count + 1

    # Close connection
    conn.close()

    # Show keys page
    return render_template("keys.html", keys=keys)


@app.route('/control', methods=['GET', 'POST'])
def control():
    if request.method == 'GET':
        # Show control page
        return render_template("control.html")

    if request.method == 'POST':
        # Get post request parameters
        cache_size = int(request.form["cache-size"])
        cache.setSize(cache_size)

        replacement = int(request.form["replace-policy"])
        cache.setReplacment(replacement)

        return redirect(url_for("statistics"))


@app.route('/clear', methods=['POST'])
def clear():
    cache.clear()
    return redirect(url_for("statistics"))


@app.route('/statistics', methods=['GET'])
def statistics():
    statistics = {}

    # Connect to database
    conn = connection()
    cursor = conn.cursor()

    # Check if their is any hit or miss count the past 10 min
    sql = "SELECT count(*) from statistics where created_at >= date_sub(now(), interval 10 minute)"
    cursor.execute(sql)

    if cursor.fetchone()[0] > 0:
        print("hi")

        # Get hit and miss rate
        sql = "SELECT SUM(hit), SUM(miss) from statistics where created_at >= date_sub(now(), interval 10 minute)"
        cursor.execute(sql)

        row = cursor.fetchone()

        #? Get hit rate
        statistics["hit_rate"] = round((row[0] / (row[0] + row[1])) * 100, 2)

        #? Get miss rate
        statistics["miss_rate"] = round(100 - statistics["hit_rate"], 2)
    else:
        statistics["hit_rate"] = "?"
        statistics["miss_rate"] = "?"

    #? Get number of items
    statistics["number_of_items"] = cache.getNumberOfItems()

    #? Get total size of the cache
    statistics["total_size"] = cache.getSize()

    #? Get Free Space in cache
    statistics["free_space"] = cache.getFreeSpace()

    #? Get replace policy
    if cache.getReplacePolicy() == 0:
        statistics["replace-policy"] = "LRU"
    else:
        statistics["replace-policy"] = "Random"

    # Show statistics page
    return render_template("statistics.html", statistics=statistics)


app.run(debug=True)
