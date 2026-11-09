from app.db import init_db
from app.config import DB_PATH,CREDENTIALS_PATH

c=init_db();c.close()
print('資料庫：',DB_PATH)
print('本機示範憑證：',CREDENTIALS_PATH)
print('注意：請不要把 runtime/ 的憑證上傳到公開儲存庫。')
