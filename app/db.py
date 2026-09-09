import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS oauth_identities(provider TEXT NOT NULL,subject TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(provider,subject));
CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,provider TEXT NOT NULL,binding TEXT NOT NULL,verifier TEXT NOT NULL,expires REAL NOT NULL,user_id INTEGER REFERENCES users(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS oauth_handoffs(binding TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,media_type TEXT NOT NULL,content TEXT NOT NULL,content_hash TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,source_id INTEGER NOT NULL,evidence_id TEXT UNIQUE NOT NULL,chunk_index INTEGER NOT NULL,content TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}',FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(source_id) REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,source_ids TEXT NOT NULL,output_type TEXT NOT NULL,path TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS connections(user_id INTEGER NOT NULL,channel TEXT NOT NULL,label TEXT NOT NULL,secret TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,channel),FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS publications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,asset_id INTEGER NOT NULL,channel TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL,result_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,fingerprint),FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT NOT NULL,object_type TEXT,object_id TEXT,details_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

def init_db():
    with sqlite3.connect(DB_PATH, timeout=30) as con:
        con.executescript(SCHEMA)
        con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE INDEX IF NOT EXISTS sources_owner ON sources(user_id,id);
        CREATE INDEX IF NOT EXISTS evidence_owner_source ON evidence(user_id,source_id);
        CREATE INDEX IF NOT EXISTS assets_owner ON assets(user_id,id);
        """)

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=ON")
        yield con
        con.commit()
    finally:
        con.close()
