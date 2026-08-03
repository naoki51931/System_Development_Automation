from sqlalchemy import select
from app.db.session import create_database_engine,create_session_factory
from app.models import MembershipRole,Organization,OrganizationMembership,Project,Role,User
from app.seed import seed_system_roles
ROLES=("customer","project_manager","reviewer","developer","organization_admin","organization_owner")
def seed(factory=None):
    factory=factory or create_session_factory(create_database_engine())
    with factory.begin() as session:
        seed_system_roles(session);session.flush();roles={r.code:r for r in session.scalars(select(Role).where(Role.code.in_(ROLES)))}
        orgs=[]
        for code in ("quality-a","quality-b"):
            org=session.scalar(select(Organization).where(Organization.name==code)) or Organization(name=code,status="active");session.add(org);session.flush();orgs.append(org)
        for code in ROLES:
            email=f"{code}@quality.local";user=session.scalar(select(User).where(User.email==email)) or User(cognito_sub=f"quality-{code}",email=email,display_name=code,status="active");session.add(user);session.flush()
            membership=session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==orgs[0].id,OrganizationMembership.user_id==user.id)) or OrganizationMembership(organization_id=orgs[0].id,user_id=user.id,status="active");session.add(membership);session.flush()
            if not session.scalar(select(MembershipRole).where(MembershipRole.membership_id==membership.id,MembershipRole.role_id==roles[code].id)):session.add(MembershipRole(membership_id=membership.id,role_id=roles[code].id))
        outsider=session.scalar(select(User).where(User.email=="outsider@quality.local")) or User(cognito_sub="quality-outsider",email="outsider@quality.local",display_name="outsider",status="active");session.add(outsider);session.flush();member=session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==orgs[1].id,OrganizationMembership.user_id==outsider.id)) or OrganizationMembership(organization_id=orgs[1].id,user_id=outsider.id,status="active");session.add(member);session.flush();owner=roles["organization_owner"]
        if not session.scalar(select(MembershipRole).where(MembershipRole.membership_id==member.id,MembershipRole.role_id==owner.id)):session.add(MembershipRole(membership_id=member.id,role_id=owner.id))
        for index,org in enumerate(orgs,1):
            if not session.scalar(select(Project).where(Project.organization_id==org.id,Project.project_code==f"QUALITY-{index}")):session.add(Project(organization_id=org.id,project_code=f"QUALITY-{index}",name=f"Quality project {index}",status="draft",current_phase="hearing"))
if __name__=="__main__":seed()
