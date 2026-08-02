# AGENTS.md

Update this file whenever implementation changes so documentation and code stay aligned.

## Application structure

- `app/main.py`: FastAPI entry point for `/`, `/health`, `/docs`, and `/static`.
- `app/templates/index.html`: Japanese Jinja2 top-page template titled and branded `SystemNavigator AI`.
- `app/static/css/style.css`: Responsive, app-local CSS with no CDN or JavaScript dependency.
- `tests/test_app.py`: Endpoint and top-page content tests.
- `requirements.txt`: Runtime and test dependencies.

## Local startup and tests

From `/home/ubuntu/ai-platform`:

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest -q
```

`/health` must return `{"status":"ok"}` and Swagger UI remains at `/docs`.

## Docker build and verification

```bash
cd /home/ubuntu/ai-platform
docker build -t ai-platform:local .
docker rm -f ai-platform-local 2>/dev/null || true
docker run -d --name ai-platform-local -p 8000:8000 ai-platform:local
curl -i http://localhost:8000/
curl -i http://localhost:8000/health
curl -i http://localhost:8000/docs
docker logs ai-platform-local
docker rm -f ai-platform-local
```

## ECS deployment

ECR is `557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod`. Build and push the tag selected by `container_image_tag` in `environment/terraform.tfvars` (currently `v4`), then deploy through a reviewed saved Terraform plan.

```bash
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 557604519341.dkr.ecr.eu-west-2.amazonaws.com
docker tag ai-platform:local 557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:v4
docker push 557604519341.dkr.ecr.eu-west-2.amazonaws.com/ai-platform-prod:v4
cd /home/ubuntu/ai-platform/environment
terraform fmt -recursive
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out=app-v4.tfplan
terraform apply app-v4.tfplan
```

Before apply, allow replacement of only the ECS task definition when it creates a new revision and updates the ECS service. Stop if the plan destroys RDS, S3, VPC, ALB, ECS cluster, Terraform state-related resources, or any other persistent infrastructure. Never commit `terraform.tfvars`, `backend.hcl`, saved plans, state, or secrets. After apply, wait for desired 1, running 1, pending 0, then verify `/`, `/health`, and `/docs` through the ALB.
