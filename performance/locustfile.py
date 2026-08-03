from locust import HttpUser,between,task
class PortalUser(HttpUser):
    wait_time=between(.1,.5)
    def on_start(self):
        users=self.client.get("/api/v1/auth/local/users",name="login-users").json();login=self.client.post("/api/v1/auth/local/login",json={"user_id":next((u["id"] for u in users if u["email"]=="organization_owner@quality.local"),users[0]["id"])},name="login").json();self.csrf=login["csrf_token"];me=self.client.get("/api/v1/auth/me").json();self.org=me["organizations"][0]["id"];page=self.client.get(f"/api/v1/projects?organization_id={self.org}",name="projects").json();self.project=page["items"][0]["id"] if page["items"] else "";rooms=self.client.get(f"/api/v1/projects/{self.project}/chat-rooms",name="chat-rooms").json() if self.project else [];self.room=rooms[0]["id"] if rooms else ""
    @task(3)
    def projects(self):self.client.get(f"/api/v1/projects?organization_id={self.org}",name="projects")
    @task
    def project_detail(self):
        if self.project:self.client.get(f"/api/v1/projects/{self.project}",name="project-detail")
    @task(2)
    def notifications(self):self.client.get(f"/api/v1/notifications?organization_id={self.org}",name="notifications")
    @task
    def chat_list(self):
        if self.room:self.client.get(f"/api/v1/chat-rooms/{self.room}/messages",name="chat-list")
    @task
    def chat_post(self):
        if self.room:self.client.post(f"/api/v1/chat-rooms/{self.room}/messages",name="chat-post",headers={"X-CSRF-Token":self.csrf},json={"body":"local load message","message_type":"user"})
    @task
    def artifacts(self):self.client.get(f"/api/v1/artifacts?organization_id={self.org}",name="artifacts")
    @task
    def reviews(self):self.client.get(f"/api/v1/reviews?organization_id={self.org}",name="reviews")
