from api.db.db_models import db, User, Tenant, Document

try:
    db.connect()
    db.create_tables([User, Tenant, Document])
    print("Successfully connected and created all tables!")
except Exception as e:
    print(f"Error: {e}")
