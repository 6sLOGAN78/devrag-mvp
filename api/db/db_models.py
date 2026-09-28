from peewee import *
from playhouse.pool import PooledMySQLDatabase
import sys
import os

# Add root project dir to path so we can import api.config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.config import CONF

# 1. Initialize the database connection using Config Singleton
mysql_conf = CONF['mysql']
db = PooledMySQLDatabase(
    mysql_conf.get('db', 'rag_flow'),
    max_connections=32,
    stale_timeout=300,
    user=mysql_conf.get('user', 'root'),
    password=mysql_conf['password'],
    host=mysql_conf.get('host', '127.0.0.1'),
    port=int(mysql_conf.get('port', 3306))
)

import time
from datetime import datetime

# 2. Define BaseModel that handles timestamps
class BaseModel(Model):
    create_time = BigIntegerField(null=True, index=True)
    create_date = DateTimeField(null=True, index=True)
    update_time = BigIntegerField(null=True, index=True)
    update_date = DateTimeField(null=True, index=True)

    def save(self, *args, **kwargs):
        if not self.create_time:
            self.create_time = int(time.time() * 1000)
            self.create_date = datetime.now()
        self.update_time = int(time.time() * 1000)
        self.update_date = datetime.now()
        return super().save(*args, **kwargs)

class DataBaseModel(BaseModel):
    class Meta:
        database = db

# 3. Define the User Model
class User(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    access_token = CharField(max_length=255, null=True, index=True)
    nickname = CharField(max_length=100, null=False, index=True)
    password = CharField(max_length=255, null=True, index=True)
    email = CharField(max_length=255, null=False, unique=True)
    avatar = TextField(null=True)
    language = CharField(max_length=32, null=True, default="English", index=True)
    timezone = CharField(max_length=64, null=True, default="UTC+8\tAsia/Shanghai", index=True)
    is_active = CharField(max_length=1, null=False, default="1", index=True)
    is_superuser = BooleanField(null=True, default=False, index=True)
    
    class Meta:
        table_name = 'user'

# 4. Define the Tenant Model
class Tenant(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    name = CharField(max_length=100, null=True, index=True)
    public_key = CharField(max_length=255, null=True, index=True)
    llm_id = CharField(max_length=128, null=False, index=True)
    embd_id = CharField(max_length=128, null=False, index=True)
    status = CharField(max_length=1, null=True, default="1", index=True)
    
    class Meta:
        table_name = 'tenant'

# 5. Define the UserTenant Join Table
class UserTenant(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    user_id = CharField(max_length=32, null=False, index=True)
    tenant_id = CharField(max_length=32, null=False, index=True)
    role = CharField(max_length=32, null=False, help_text="owner|member", index=True)
    status = CharField(max_length=1, null=True, default="1", index=True)

    class Meta:
        table_name = 'user_tenant'

# 6. Define the Document Model
class Document(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    thumbnail = TextField(null=True)
    kb_id = CharField(max_length=256, null=False, index=True)
    parser_id = CharField(max_length=32, null=False, index=True)
    source_type = CharField(max_length=128, null=False, default='local')
    type = CharField(max_length=32, null=False)
    created_by = CharField(max_length=32, null=False)
    name = CharField(max_length=255, null=True)
    location = CharField(max_length=255, null=True)
    size = BigIntegerField(default=0)
    token_num = IntegerField(default=0)
    chunk_num = IntegerField(default=0)
    progress = FloatField(default=0.0)
    progress_msg = TextField(null=True)
    status = CharField(max_length=1, null=True, default='1', index=True)
    
    class Meta:
        table_name = 'document'


# 7. Define Knowledgebase Model
class Knowledgebase(DataBaseModel):
    id = CharField(max_length=32, primary_key=True)
    avatar = TextField(null=True, help_text="avatar base64 string")
    tenant_id = CharField(max_length=32, null=False, index=True)
    name = CharField(max_length=128, null=False, index=True)
    language = CharField(max_length=32, null=True, default="English", index=True)
    description = TextField(null=True)
    embd_id = CharField(max_length=128, null=False, index=True)
    permission = CharField(max_length=16, null=False, default="me", index=True)
    created_by = CharField(max_length=32, null=False, index=True)
    doc_num = IntegerField(default=0, index=True)
    token_num = IntegerField(default=0, index=True)
    chunk_num = IntegerField(default=0, index=True)
    similarity_threshold = FloatField(default=0.2, index=True)
    vector_similarity_weight = FloatField(default=0.3, index=True)

    parser_id = CharField(max_length=32, null=False, default="naive", index=True)
    parser_config = TextField(null=False, default='{"pages": [[1, 1000000]]}')
    status = CharField(max_length=1, null=True, default="1", index=True)

    class Meta:
        table_name = 'knowledgebase'

# 8. Connect and create the tables!
if __name__ == '__main__':
    db.connect()
    # Safely create tables (migrations)
    db.create_tables([User, Tenant, UserTenant, Document, Knowledgebase], safe=True)
    print("Database migrations applied successfully!")
    db.close()
