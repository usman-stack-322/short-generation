"""Local operator bootstrap/reset. Web registration never grants administration."""
import argparse,getpass,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.migrate import migrate_database
from app.database.session import SessionLocal
from app.core.security import hash_password,new_id
from app.models import User,Workspace,WorkspaceMember


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--email',required=True);parser.add_argument('--name',default='Platform Owner');parser.add_argument('--reset-password',action='store_true');args=parser.parse_args()
    password=getpass.getpass('New password (at least 12 characters): ')
    if len(password)<12 or password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords must match and contain at least 12 characters')
    migrate_database()
    with SessionLocal() as db:
        user=db.query(User).filter_by(email=args.email.lower()).first()
        if user:
            member=db.query(WorkspaceMember).filter_by(user_id=user.id).first()
            if not args.reset_password or not member or member.role!='OWNER':raise SystemExit('Existing accounts require --reset-password and an existing Owner role; use Admin Panel for role changes')
            user.password_hash=hash_password(password)
        else:
            if db.query(WorkspaceMember).filter_by(role='OWNER',active=True).count():raise SystemExit('An Owner exists. Use Admin Panel to appoint additional administrators')
            user=User(id=new_id(),email=args.email.lower(),name=args.name,password_hash=hash_password(password));space=Workspace(id=new_id(),name='Owner workspace')
            db.add_all([user,space]);db.flush();db.add(WorkspaceMember(id=new_id(),user_id=user.id,workspace_id=space.id,role='OWNER'))
        db.commit()
    print('Owner account saved. No demo data created.')


if __name__=='__main__':main()
