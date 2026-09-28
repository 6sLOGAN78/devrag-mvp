from quart import Quart, jsonify
from api.db.db_models import db
from api.utils import redis_conn, storage_client
from api.apps.user_app import user_app
from api.apps.kb_app import kb_app

app = Quart(__name__)
app.register_blueprint(user_app)
app.register_blueprint(kb_app)

def check_db():
    try:
        db.execute_sql("SELECT 1")
        return True, {"status": "ok", "elapsed": "0.0"}
    except Exception as e:
        return False, {"status": "nok", "error": str(e)}

@app.route('/health', methods=['GET'])
async def health():
    return jsonify({"status": "ok", "engine": "python"})

@app.route('/api/v1/system/healthz', methods=['GET'])
@app.route('/api/health', methods=['GET'])
async def api_health():
    is_ok, db_status = check_db()
    return jsonify({
        "status": "ok" if is_ok else "nok",
        "engine": "python",
        "db": db_status
    })

if __name__ == '__main__':
    # Run the Quart server on port 9380 to match NGINX expectations
    app.run(host='0.0.0.0', port=9380)
