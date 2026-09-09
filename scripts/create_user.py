import argparse
import getpass
import sqlite3
from app.db import init_db, db
from app.security import hash_password

def main():
    parser = argparse.ArgumentParser(description='Create a local NTRO account')
    parser.add_argument('username')
    parser.add_argument('password', nargs='?', help='Omit for a hidden password prompt')
    args = parser.parse_args()
    password = args.password or getpass.getpass('Password: ')
    if not args.username.strip() or len(args.username) > 100 or not password or len(password) > 1024:
        parser.error('Provide a username (1-100 chars) and password (1-1024 chars)')
    init_db()
    try:
        with db() as con:
            con.execute('INSERT INTO users(username,password_hash) VALUES(?,?)', (args.username, hash_password(password)))
    except sqlite3.IntegrityError:
        parser.exit(1, 'That username already exists.\n')
    print('Created user:', args.username)

if __name__ == '__main__':
    main()
