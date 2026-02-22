import sqlite3, os
print('exists', os.path.exists('test.db'))
if os.path.exists('test.db'):
    conn = sqlite3.connect('test.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(cur.fetchall())
    conn.close()