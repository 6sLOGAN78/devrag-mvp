import yaml
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '../conf/service_conf.yaml')

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}. Please run generate_conf.sh first.")
        
    with open(CONFIG_PATH, 'r') as file:
        config = yaml.safe_load(file)
        
    # Fail-Fast Validation
    if not config.get('mysql', {}).get('password'):
        raise ValueError("CRITICAL: mysql.password is missing in configuration! Refusing to start.")
        
    return config

# Singleton instance
CONF = load_config()

if __name__ == '__main__':
    # Test execution
    print("Configuration loaded successfully!")
    print(f"MySQL Host: {CONF['mysql']['host']}")
