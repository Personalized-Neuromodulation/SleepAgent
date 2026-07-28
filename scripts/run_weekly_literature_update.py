from sleep_ai_scientist.literature_db.config import load_literature_db_config
from sleep_ai_scientist.literature_db.engine import create_database_engine,init_database,session_scope
from sleep_ai_scientist.literature_db.weekly_update import run_weekly_update

if __name__ == "__main__":
    config_path="configs/literature_database.yaml";config=load_literature_db_config(config_path);engine=create_database_engine(config_path);init_database(engine)
    with session_scope(engine) as session:print(run_weekly_update(session,config))
