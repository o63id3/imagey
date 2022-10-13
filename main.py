from flask import Flask, render_template, request, redirect, url_for
import pymysql
import os
import time

app = Flask(__name__)


class Cache:
    def __init__(self, capacity: int):
        self.cache = dict()
        self.capacity = capacity
        self.size = 0
        self.hit_count = 0
        self.miss_count = 0
    
    def get(self, key: int) -> int:
        pass
    
    def put(self, key: int, value: int) -> None:
        pass
    
    def replace(self, ):
        pass
    
    def setReplacment(self, ):
        pass
    
    def setCapacity(self, ):
        pass
    
    def getCapacity(self, ) -> int:
        return self.capacity


#! Cache
cache = Cache(1000)


def connection():
    # Connect to database
    conn = pymysql.connect(host='localhost', user='root', password='', database='imagey')
    return conn


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
        
        if cursor.fetchall()[0][0] == 0:
            # If hash does not exist insert to database
            sql = f"INSERT INTO images (hash, image) VALUES ('{hash}', '{file_name}')"
        else:
            #! Delete the old image form disk
            sql = f"select image from images where hash='{hash}'"
            cursor.execute(sql)
            old_image = cursor.fetchall()[0][0]
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
        # Connect to database
        conn = connection()
        
        # Get post request parameters
        hash = str(request.form["hash"])
        
        # Create new cursor
        cursor = conn.cursor()
        
        # Check if hash exists
        sql = f"SELECT count(*) FROM `images` WHERE hash='{hash}'"
        cursor.execute(sql)
        
        if cursor.fetchall()[0][0] == 0:
            # # Store request to database as NOT_FOUND request
            # sql = f"INSERT INTO requests (hash, status) VALUES ('{hash}', 'NOT_FOUND')"
            # cursor.execute(sql)
            
            # # Commit changes
            # conn.commit()
            
            # # Close connection
            # conn.close()
            
            # If hash does not exist redirct to same page with error message
            return render_template("get.html", hash=hash, message="Hash not found!")
        else:          
            # If hash exists redirct to same page with the image
            sql = f"select image from images where hash='{hash}'"
            cursor.execute(sql)
            image = f"/static/uploaded images/{cursor.fetchall()[0][0]}"
            
            # Commit changes
            conn.commit()
            
            # Close connection
            conn.close()
            
            # Show get page
            return render_template("get.html", hash=hash, image=image)


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


@app.route('/control', methods=['GET'])
def control():
    if request.method == 'GET':
        # Show control page
        return render_template("control.html")
    
    if request.method == 'POST':
        pass


@app.route('/statistics', methods=['GET'])
def statistics():
    # # Connect to database
    # conn = connection()
    
    # # Create new cursor
    # cursor = conn.cursor()
    
    # statistics = {}
    
    # #? Get total requests without NOT_FOUND
    # sql = "select count(*) from requests where status!='NOT_FOUND'"
    # cursor.execute(sql)
    # total_reauests = cursor.fetchall()[0][0]
    
    # if total_reauests == 0:
    #     #? Get hit rate
    #     statistics["hit_rate"] = 100
    
    #     #? Get miss rate
    #     statistics["miss_rate"] = 0
    # else:
    #     #? Get hit rate
    #     sql = "select count(*) from requests where status='HIT'"
    #     cursor.execute(sql)
    #     statistics["hit_rate"] = "{0:.2f}".format(cursor.fetchall()[0][0] / total_reauests * 100)
    
    #     #? Get miss rate
    #     statistics["miss_rate"] = 100 - float(statistics["hit_rate"])
    
    # #! Get number of items
    # statistics["number_of_items"] = 30
    
    # #! Get total size of the cache
    # statistics["total_size"] = cache.getCapacity()
    
    # #? Get number of requests
    # sql = "select count(*) from requests"
    # cursor.execute(sql)
    # statistics["number_of_requests"] = cursor.fetchall()[0][0]
    
    # Show statistics page
    return render_template("statistics.html", statistics=statistics)


app.run(debug = True)
