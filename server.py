"""Local full-stack test server for Afaq School Platform.
Run: python3 server.py   then open http://localhost:8000
"""
import base64, json, mimetypes, os, sqlite3, uuid
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent
DB = ROOT / "afaq.db"
UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, role TEXT NOT NULL, grade TEXT, section TEXT, job TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS submissions (
      id INTEGER PRIMARY KEY, student TEXT NOT NULL, grade TEXT, section TEXT,
      kind TEXT NOT NULL, text TEXT NOT NULL, file_url TEXT, file_name TEXT,
      score REAL, status TEXT NOT NULL DEFAULT 'pending', owner_email TEXT, owner_name TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS certificates (
      id INTEGER PRIMARY KEY, owner_email TEXT NOT NULL, owner_name TEXT NOT NULL,
      title TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS stories (
      id INTEGER PRIMARY KEY, student TEXT NOT NULL, grade TEXT, section TEXT,
      author TEXT NOT NULL, author_email TEXT, source_role TEXT NOT NULL, text TEXT NOT NULL,
      file_url TEXT, file_name TEXT, score REAL, published INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS class_scores (
      id INTEGER PRIMARY KEY, grade TEXT NOT NULL, section TEXT NOT NULL,
      environment REAL NOT NULL, attendance REAL NOT NULL, activities REAL NOT NULL,
      digital REAL NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(grade, section)
    );
    CREATE TABLE IF NOT EXISTS class_winners (
      grade TEXT PRIMARY KEY, section TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    try: c.execute("ALTER TABLE submissions ADD COLUMN owner_email TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE submissions ADD COLUMN owner_name TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE stories ADD COLUMN author_email TEXT")
    except sqlite3.OperationalError: pass
    c.execute("INSERT OR IGNORE INTO settings VALUES ('zayed_value','التسامح')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('positive_value','المساواة')")
    c.commit(); c.close()

def rows(c, query, args=()): return [dict(r) for r in c.execute(query, args).fetchall()]
def now(): return datetime.now().isoformat(timespec="seconds")

class API(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): print("[afaq]", fmt % args)
    def json(self, status, payload):
        raw=json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def body(self):
        size=int(self.headers.get("Content-Length",0)); return json.loads(self.rfile.read(size) or b"{}")
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith("/api/"): return self.get_api(path)
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        if path.startswith("/api/"): return self.post_api(path)
        self.json(404,{"error":"Not found"})
    def get_api(self,path):
        c=conn()
        if path=="/api/health": out={"ok":True}
        elif path=="/api/users":
            prefix=parse_qs(urlparse(self.path).query).get("prefix",[""])[0].lower()
            out=rows(c,"SELECT name,email,role FROM users WHERE lower(email) LIKE ? ORDER BY email LIMIT 8",(prefix+"%",))
        elif path=="/api/settings": out={r['key']:r['value'] for r in c.execute("SELECT * FROM settings")}
        elif path=="/api/review": out={"submissions":rows(c,"SELECT * FROM submissions ORDER BY id DESC"),"stories":rows(c,"SELECT * FROM stories ORDER BY id DESC")}
        elif path=="/api/student-activity":
            student=parse_qs(urlparse(self.path).query).get("student",[""])[0]
            out={"submissions":rows(c,"SELECT * FROM submissions WHERE student=? ORDER BY id DESC",(student,)),"stories":rows(c,"SELECT * FROM stories WHERE student=? ORDER BY id DESC",(student,))}
        elif path=="/api/parent-requests":
            author=parse_qs(urlparse(self.path).query).get("author",[""])[0]
            out=rows(c,"SELECT * FROM stories WHERE author=? AND source_role='parent' ORDER BY id DESC",(author,))
        elif path=="/api/certificates":
            email=parse_qs(urlparse(self.path).query).get("email",[""])[0].lower()
            out=rows(c,"SELECT * FROM certificates WHERE owner_email=? ORDER BY id DESC",(email,))
        elif path=="/api/public/stories": out=rows(c,"SELECT * FROM stories WHERE published=1 ORDER BY id DESC")
        elif path=="/api/public/home":
            values={r['key']:r['value'] for r in c.execute("SELECT * FROM settings")}
            out={"values":values,"stories":rows(c,"SELECT * FROM submissions WHERE kind='سلوك إيجابي' AND status='accepted' ORDER BY id DESC LIMIT 3"),"family_stories":rows(c,"SELECT * FROM stories WHERE published=1 AND source_role='parent' ORDER BY id DESC LIMIT 3"),"ambassadors":rows(c,"SELECT student,grade,section FROM submissions WHERE kind='طلب سفيرة الميثاق' AND status='accepted' ORDER BY id DESC"),"class_winners":rows(c,"SELECT grade,section FROM class_winners ORDER BY grade"),"counts":{"participations":c.execute("SELECT count(*) FROM submissions WHERE kind!='طلب سفيرة الميثاق'").fetchone()[0],"stories":c.execute("SELECT count(*) FROM submissions WHERE kind='سلوك إيجابي' AND status='accepted'").fetchone()[0],"ambassadors":c.execute("SELECT count(*) FROM submissions WHERE kind='طلب سفيرة الميثاق' AND status='accepted'").fetchone()[0]}}
        elif path=="/api/class-scores": out=rows(c,"SELECT *, environment+attendance+activities+digital AS total FROM class_scores ORDER BY grade, total DESC")
        elif path=="/api/class-winners": out=rows(c,"SELECT * FROM class_winners ORDER BY grade")
        elif path=="/api/stats":
            out={"users":c.execute("SELECT count(*) FROM users").fetchone()[0],"students":c.execute("SELECT count(*) FROM users WHERE role='student'").fetchone()[0],"submissions":c.execute("SELECT count(*) FROM submissions").fetchone()[0],"stories":c.execute("SELECT count(*) FROM stories WHERE published=1").fetchone()[0],"pending":c.execute("SELECT count(*) FROM submissions WHERE status='pending'").fetchone()[0]+c.execute("SELECT count(*) FROM stories WHERE score IS NULL").fetchone()[0]}
        else: c.close(); return self.json(404,{"error":"Unknown API endpoint"})
        c.close(); self.json(200,out)
    def save_file(self, file):
        if not file or not file.get("data"): return None,None
        payload=file["data"].split(",",1)[-1]
        raw=base64.b64decode(payload)
        if len(raw)>100*1024*1024: raise ValueError("الحد الأقصى للفيديو هو 100 MB")
        original=Path(file.get("name") or "evidence").name
        stored=f"{uuid.uuid4().hex}_{original}"
        (UPLOADS/stored).write_bytes(raw)
        return f"/uploads/{stored}",original
    def post_api(self,path):
        try: b=self.body()
        except Exception: return self.json(400,{"error":"بيانات غير صالحة"})
        c=conn()
        try:
            if path=="/api/auth/register":
                c.execute("INSERT INTO users(name,email,password,role,grade,section,job,created_at) VALUES(?,?,?,?,?,?,?,?)",(b['name'],b['email'].lower(),b['password'],b['role'],b.get('grade',''),b.get('section',''),b.get('job',''),now()))
                c.commit(); out={"ok":True,"user":dict(c.execute("SELECT id,name,email,role,grade,section,job FROM users WHERE email=?",(b['email'].lower(),)).fetchone())}
            elif path=="/api/auth/login":
                u=c.execute("SELECT id,name,email,role,grade,section,job FROM users WHERE email=? AND password=?",(b['email'].lower(),b['password'])).fetchone()
                if not u: c.close(); return self.json(401,{"error":"الإيميل أو كلمة المرور غير صحيحة"})
                out={"ok":True,"user":dict(u)}
            elif path=="/api/submissions":
                email=b.get('owner_email','').lower()
                if email and c.execute("SELECT 1 FROM submissions WHERE owner_email=? AND kind=?",(email,b['kind'])).fetchone(): raise ValueError('لقد أرسلتِ دليل هذه القيمة بالفعل. انتظري القيمة الجديدة من نائب المدير.')
                url,name=self.save_file(b.get("file")); c.execute("INSERT INTO submissions(student,grade,section,kind,text,file_url,file_name,owner_email,owner_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(b['student'],b.get('grade',''),b.get('section',''),b['kind'],b['text'],url,name,email,b.get('owner_name',''),now()));c.commit();out={"ok":True}
            elif path=="/api/certificates":
                c.execute("INSERT INTO certificates(owner_email,owner_name,title,detail,created_at) VALUES(?,?,?,?,?)",(b['owner_email'].lower(),b['owner_name'],b['title'],b['detail'],now()));c.commit();out={"ok":True}
            elif path=="/api/stories":
                url,name=self.save_file(b.get("file"));c.execute("INSERT INTO stories(student,grade,section,author,author_email,source_role,text,file_url,file_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(b['student'],b.get('grade',''),b.get('section',''),b['author'],b.get('author_email','').lower(),b['source_role'],b['text'],url,name,now()));c.commit();out={"ok":True}
            elif path=="/api/review/submission":
                score=float(b['score']); assert 0<=score<=5;c.execute("UPDATE submissions SET score=?,status='reviewed' WHERE id=?",(score,b['id']));c.commit();out={"ok":True}
            elif path=="/api/review/behavior":
                status=b['status']; assert status in ('accepted','rejected');row=c.execute("SELECT * FROM submissions WHERE id=?",(b['id'],)).fetchone();
                if not row: raise ValueError('الترشيح غير موجود')
                c.execute("UPDATE submissions SET status=? WHERE id=?",(status,b['id']))
                if status=='accepted':
                    email=(row['owner_email'] or '').lower()
                    recipient=row['owner_name'] or ''
                    if not email:
                        u=c.execute("SELECT name,email FROM users WHERE name=? AND role='teacher' ORDER BY id DESC LIMIT 1",(recipient or row['student'],)).fetchone(); email=u['email'] if u else ''; recipient=recipient or (u['name'] if u else '')
                    elif not recipient:
                        u=c.execute("SELECT name FROM users WHERE email=?",(email,)).fetchone(); recipient=u['name'] if u else ''
                    if email and not c.execute("SELECT 1 FROM certificates WHERE owner_email=? AND title=? AND detail=?",(email,'شهادة شكر وتقدير','خالص الامتنان لجهودك المباركة')).fetchone():
                        c.execute("INSERT INTO certificates(owner_email,owner_name,title,detail,created_at) VALUES(?,?,?,?,?)",(email,recipient,'شهادة شكر وتقدير','خالص الامتنان لجهودك المباركة',now()))
                c.commit();out={"ok":True}
            elif path=="/api/review/ambassador":
                status=b['status']; assert status in ('accepted','rejected');c.execute("UPDATE submissions SET status=? WHERE id=?",(status,b['id']));c.commit();out={"ok":True}
            elif path=="/api/review/story":
                score=float(b['score']); assert 0<=score<=5;row=c.execute("SELECT * FROM stories WHERE id=?",(b['id'],)).fetchone();
                if not row: raise ValueError('القصة غير موجودة')
                published=1 if b.get('published') else 0;c.execute("UPDATE stories SET score=?,published=? WHERE id=?",(score,published,b['id']))
                if published and row['source_role']=='parent':
                    email=(row['author_email'] or '').lower()
                    if not email:
                        u=c.execute("SELECT email FROM users WHERE name=? AND role='parent' ORDER BY id DESC LIMIT 1",(row['author'],)).fetchone(); email=u['email'] if u else ''
                    phrase='تقديراً لمشاركتكم بأفعال ابنكم، ممتنون لتعاونكم معنا'
                    if email and not c.execute("SELECT 1 FROM certificates WHERE owner_email=? AND title=? AND detail=?",(email,'شهادة شكر وتقدير',phrase)).fetchone():
                        c.execute("INSERT INTO certificates(owner_email,owner_name,title,detail,created_at) VALUES(?,?,?,?,?)",(email,row['author'],'شهادة شكر وتقدير',phrase,now()))
                c.commit();out={"ok":True}
            elif path=="/api/settings":
                for key in ('zayed_value','positive_value'): c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",(key,b[key]));c.commit()
                out={"ok":True}
            elif path=="/api/class-scores":
                values=(b['grade'],b['section'],float(b['environment']),float(b['attendance']),float(b['activities']),float(b['digital']),now())
                if any(x<0 or x>5 for x in values[2:6]): raise ValueError('كل الدرجات من 0 إلى 5')
                c.execute("INSERT INTO class_scores(grade,section,environment,attendance,activities,digital,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(grade,section) DO UPDATE SET environment=excluded.environment,attendance=excluded.attendance,activities=excluded.activities,digital=excluded.digital,created_at=excluded.created_at",values);c.commit();out={"ok":True}
            elif path=="/api/class-winners":
                for grade in ('5','6','7'):
                    section=b[grade]; assert section in ('A','B','C')
                    c.execute("INSERT INTO class_winners(grade,section,updated_at) VALUES(?,?,?) ON CONFLICT(grade) DO UPDATE SET section=excluded.section,updated_at=excluded.updated_at",(grade,section,now()))
                c.commit();out={"ok":True}
            else: c.close(); return self.json(404,{"error":"Unknown API endpoint"})
        except sqlite3.IntegrityError: c.close(); return self.json(409,{"error":"هذا الإيميل مسجل مسبقًا"})
        except (KeyError,ValueError,AssertionError) as e: c.close(); return self.json(400,{"error":str(e) or 'تحققي من البيانات'})
        c.close(); self.json(200,out)

if __name__=="__main__":
    os.chdir(ROOT); init_db(); print("Afaq running: http://localhost:8000"); ThreadingHTTPServer(("",8000),API).serve_forever()
