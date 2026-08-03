import os,uuid
from datetime import datetime,timezone
from app.db.session import create_database_engine,create_session_factory
from app.models import AuditLog,ChatMessage,ChatRoom,Notification,Organization,OrganizationMembership,Project,User

def scaled(name,default):return max(1,int(int(os.getenv(name,default))*float(os.getenv("QUALITY_SCALE","0.01"))))
def main():
    target={"organizations":scaled("QUALITY_ORGANIZATIONS",10),"users":scaled("QUALITY_USERS",1000),"projects":scaled("QUALITY_PROJECTS",5000),"chat_messages":scaled("QUALITY_CHAT_MESSAGES",100000),"notifications":scaled("QUALITY_NOTIFICATIONS",100000),"audit_logs":scaled("QUALITY_AUDIT_LOGS",100000)}
    factory=create_session_factory(create_database_engine())
    with factory.begin() as s:
        orgs=[Organization(name=f"perf-org-{uuid.uuid4().hex[:8]}") for _ in range(target["organizations"])];s.add_all(orgs);s.flush()
        users=[User(cognito_sub=f"perf-{uuid.uuid4()}",email=f"perf-{uuid.uuid4().hex}@quality.local",display_name="Performance user") for _ in range(target["users"])];s.add_all(users);s.flush()
        s.add_all([OrganizationMembership(organization_id=orgs[i%len(orgs)].id,user_id=u.id,status="active") for i,u in enumerate(users)]);s.flush()
        projects=[Project(organization_id=orgs[i%len(orgs)].id,project_code=f"PERF-{uuid.uuid4().hex[:12]}",name="Performance project",status="draft",current_phase="hearing") for i in range(target["projects"])];s.add_all(projects);s.flush()
        member=next(u for i,u in enumerate(users) if orgs[i%len(orgs)].id==projects[0].organization_id);room=ChatRoom(organization_id=projects[0].organization_id,project_id=projects[0].id,room_type="project",name="Performance room",status="active",created_by_user_id=member.id);s.add(room);s.flush()
        now=datetime.now(timezone.utc)
        s.bulk_insert_mappings(ChatMessage,[{"id":uuid.uuid4(),"organization_id":projects[0].organization_id,"project_id":projects[0].id,"chat_room_id":room.id,"sender_user_id":member.id,"message_type":"user","body":f"message {i}","status":"active","version":1,"created_at":now} for i in range(target["chat_messages"])])
        s.bulk_insert_mappings(Notification,[{"id":uuid.uuid4(),"organization_id":projects[0].organization_id,"user_id":member.id,"event_type":"performance","title":"Performance","body":f"notification {i}","severity":"info","status":"pending","deduplication_key":f"perf:{uuid.uuid4()}","version":1,"created_at":now} for i in range(target["notifications"])])
        s.bulk_insert_mappings(AuditLog,[{"id":uuid.uuid4(),"organization_id":projects[0].organization_id,"actor_user_id":member.id,"action":"performance.read","resource_type":"quality","request_id":uuid.uuid4(),"created_at":now} for _ in range(target["audit_logs"])])
    print(target)
if __name__=="__main__":main()
