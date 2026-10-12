from app.db.session import SessionLocal
from app.seed.csv_tickets import remap_tickets_to_csv


if __name__ == "__main__":
    with SessionLocal() as session:
        print(remap_tickets_to_csv(session))
