variable "name_prefix" {
  type = string
}
variable "aws_region" {
  type = string
}
variable "vpc_id" {
  type = string
}
variable "application_sg_id" {
  type = string
}
variable "public_subnet_ids" {
  type = list(string)
}
variable "private_subnet_ids" {
  type = list(string)
}
variable "backend_image" {
  type = string
}
variable "worker_image" {
  type = string
}
variable "frontend_image" {
  type = string
}
variable "desired_count_backend" {
  type = number
}
variable "desired_count_worker" {
  type = number
}
variable "desired_count_frontend" {
  type = number
}
variable "log_retention_days" {
  type = number
}
variable "artifact_bucket_arn" {
  type    = string
  default = null
}
variable "application_database_secret_arn" {
  type      = string
  sensitive = true
}
variable "migration_database_secret_arn" {
  type      = string
  sensitive = true
}
variable "application_secret_arns" {
  type = list(string)
}
variable "enable_mock_ai" {
  type = bool
}
variable "enable_mock_payment" {
  type = bool
}
variable "enable_mock_email" {
  type = bool
}
variable "enable_cognito" {
  type = bool
}
variable "enable_stripe" {
  type = bool
}
variable "enable_ses" {
  type = bool
}
variable "enable_s3_storage" {
  type = bool
}
variable "stripe_mode" {
  type = string
}
variable "enable_https" {
  type = bool
}
variable "acm_certificate_arn" {
  type = string
}
variable "cognito_user_pool_id" {
  type = string
}
variable "cognito_app_client_id" {
  type = string
}
variable "cognito_issuer" {
  type = string
}
variable "cognito_domain" {
  type = string
}
variable "stripe_publishable_key" {
  type = string
}
variable "stripe_webhook_endpoint" {
  type = string
}
variable "ses_region" {
  type = string
}
variable "ses_from_address" {
  type = string
}
variable "ses_configuration_set" {
  type = string
}
variable "ses_sandbox_mode" {
  type = bool
}

locals {
  services = {
    backend = {
      port = 8000, desired = var.desired_count_backend
    }
    worker = {
      port = 0, desired = var.desired_count_worker
    }
    frontend = {
      port = 3000, desired = var.desired_count_frontend
    }

  }
  common_environment = [
    {
      name = "APP_ENV", value = "staging"
    },
    {
      name = "APP_LOCAL_AUTH_ENABLED", value = "false"
    },
    {
      name = "APP_ENABLE_MOCK_AI", value = tostring(var.enable_mock_ai)
    },
    {
      name = "APP_ENABLE_MOCK_PAYMENT", value = tostring(var.enable_mock_payment)
    },
    {
      name = "APP_ENABLE_MOCK_EMAIL", value = tostring(var.enable_mock_email)
    },
    {
      name = "APP_ENABLE_COGNITO", value = tostring(var.enable_cognito)
    },
    {
      name = "APP_ENABLE_STRIPE", value = tostring(var.enable_stripe)
    },
    {
      name = "APP_ENABLE_SES", value = tostring(var.enable_ses)
    },
    {
      name = "APP_ENABLE_S3_STORAGE", value = tostring(var.enable_s3_storage)
    },
    {
      name = "APP_STRIPE_MODE", value = var.stripe_mode
    },
    {
      name = "APP_COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id
    },
    {
      name = "APP_COGNITO_APP_CLIENT_ID", value = var.cognito_app_client_id
    },
    {
      name = "APP_COGNITO_ISSUER", value = var.cognito_issuer
    },
    {
      name = "APP_COGNITO_DOMAIN", value = var.cognito_domain
    },
    {
      name = "APP_STRIPE_PUBLISHABLE_KEY", value = var.stripe_publishable_key
    },
    {
      name = "APP_STRIPE_WEBHOOK_ENDPOINT", value = var.stripe_webhook_endpoint
    },
    {
      name = "APP_SES_REGION", value = var.ses_region
    },
    {
      name = "APP_SES_FROM_ADDRESS", value = var.ses_from_address
    },
    {
      name = "APP_SES_CONFIGURATION_SET", value = var.ses_configuration_set
    },
    {
      name = "APP_SES_SANDBOX_MODE", value = tostring(var.ses_sandbox_mode)
    },
  ]
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }, Action = "sts:AssumeRole"
    }]

  })
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(["backend", "worker", "frontend", "migration"])
  name              = "/system-navigator/staging/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Staging ALB ingress"
  vpc_id      = var.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  dynamic "ingress" {
    for_each = var.enable_https ? [1] : []
    content {
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }

  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_vpc_security_group_ingress_rule" "backend_alb" {
  security_group_id            = var.application_sg_id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "backend_internal" {
  security_group_id            = var.application_sg_id
  referenced_security_group_id = var.application_sg_id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "frontend_alb" {
  security_group_id            = var.application_sg_id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 3000
  to_port                      = 3000
  ip_protocol                  = "tcp"
}

resource "aws_lb" "main" {
  name                       = substr("${var.name_prefix}-alb", 0, 32)
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
}
resource "aws_lb_target_group" "backend" {
  name        = substr("${var.name_prefix}-be", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/health"
    matcher = "200-399"
  }
}
resource "aws_lb_target_group" "frontend" {
  name        = substr("${var.name_prefix}-fe", 0, 32)
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/"
    matcher = "200-399"
  }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  dynamic "default_action" {
    for_each = var.enable_https ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

  }
  dynamic "default_action" {
    for_each = var.enable_https ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.frontend.arn
    }

  }
  lifecycle {
    precondition {
      condition     = !var.enable_https || var.acm_certificate_arn != ""
      error_message = "HTTPS requires an ACM certificate ARN."
    }

  }
}
resource "aws_lb_listener" "https" {
  count             = var.enable_https ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}
resource "aws_lb_listener_rule" "backend_http" {
  count        = var.enable_https ? 0 : 1
  listener_arn = aws_lb_listener.http.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json"]
    }
  }
}
resource "aws_lb_listener_rule" "backend_https" {
  count        = var.enable_https ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json"]
    }
  }
}

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "staging.system-navigator.internal"
  vpc  = var.vpc_id
}
resource "aws_service_discovery_service" "internal" {
  for_each = toset(["backend", "worker"])
  name     = each.key
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"

  }
  health_check_custom_config {}
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-task-execution"
  assume_role_policy = local.assume_role_policy
}
resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = concat([var.application_database_secret_arn, var.migration_database_secret_arn], var.application_secret_arns)

  }
}
resource "aws_iam_role_policy" "execution_secrets" {
  name   = "staging-task-secret-injection"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}
resource "aws_iam_role" "task" {
  for_each           = toset(["backend", "worker", "frontend", "migration"])
  name               = "${var.name_prefix}-${each.key}-task"
  assume_role_policy = local.assume_role_policy
}
data "aws_iam_policy_document" "backend" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = concat([var.application_database_secret_arn], var.application_secret_arns)
  }
}
resource "aws_iam_role_policy" "backend" {
  name   = "runtime-secrets"
  role   = aws_iam_role.task["backend"].id
  policy = data.aws_iam_policy_document.backend.json
}
data "aws_iam_policy_document" "worker" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = concat([var.application_database_secret_arn], var.application_secret_arns)
  }
  dynamic "statement" {
    for_each = var.artifact_bucket_arn == null ? [] : [1]
    content {
      actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      resources = [var.artifact_bucket_arn, "${var.artifact_bucket_arn}/*"]
    }

  }
}
resource "aws_iam_role_policy" "worker" {
  name   = "worker-runtime"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.worker.json
}
data "aws_iam_policy_document" "migration" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.migration_database_secret_arn]
  }
}
resource "aws_iam_role_policy" "migration" {
  name   = "database-secret-only"
  role   = aws_iam_role.task["migration"].id
  policy = data.aws_iam_policy_document.migration.json
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["backend"].arn
  container_definitions = jsonencode([{
    name = "backend", image = var.backend_image, essential = true, command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], portMappings = [{
      containerPort = 8000
      }], environment = local.common_environment, secrets = [{
      name = "APP_DATABASE_SECRET_JSON", valueFrom = var.application_database_secret_arn
      }], healthCheck = {
      command = ["CMD-SHELL", "python -c \"__import__('urllib.request').request.urlopen('http://localhost:8000/health')\""], interval = 30, timeout = 5, retries = 3
      }, logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.service["backend"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "backend"
      }
    }
  }])
}
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["worker"].arn
  container_definitions = jsonencode([{
    name = "worker", image = var.worker_image, essential = true, command = ["python", "-m", "app.workers.runner"], environment = local.common_environment, secrets = [{
      name = "APP_DATABASE_SECRET_JSON", valueFrom = var.application_database_secret_arn
      }], healthCheck = {
      command = ["CMD-SHELL", "python -m app.workers.health"], interval = 30, timeout = 10, retries = 3
      }, logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.service["worker"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "worker"
      }
    }
  }])
}
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["frontend"].arn
  container_definitions = jsonencode([{
    name = "frontend", image = var.frontend_image, essential = true, command = ["node", "server.js"], portMappings = [{
      containerPort = 3000
      }], environment = [
      { name = "APP_ENV", value = "staging" },
      { name = "APP_ENABLE_MOCK_AI", value = tostring(var.enable_mock_ai) },
      { name = "APP_ENABLE_MOCK_PAYMENT", value = tostring(var.enable_mock_payment) },
      { name = "APP_ENABLE_MOCK_EMAIL", value = tostring(var.enable_mock_email) }
      ], healthCheck = {
      command = ["CMD-SHELL", "wget -q -O /dev/null http://localhost:3000/ || exit 1"], interval = 30, timeout = 5, retries = 3
      }, logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.service["frontend"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "frontend"
      }
    }
  }])
}
resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name_prefix}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task["migration"].arn
  container_definitions = jsonencode([{
    name = "migration", image = var.backend_image, essential = true, command = ["alembic", "upgrade", "head"], environment = [{
      name = "APP_ENV", value = "staging"
      }, {
      name = "APP_LOCAL_AUTH_ENABLED", value = "false"
      }], secrets = [{
      name = "APP_DATABASE_SECRET_JSON", valueFrom = var.migration_database_secret_arn
      }], logConfiguration = {
      logDriver = "awslogs", options = {
        awslogs-group = aws_cloudwatch_log_group.service["migration"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "migration"
      }
    }
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count_backend
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.application_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }
  service_registries {
    registry_arn = aws_service_discovery_service.internal["backend"].arn
  }
  health_check_grace_period_seconds = 60
  depends_on                        = [aws_lb_listener.http, aws_lb_listener.https]
}
resource "aws_ecs_service" "worker" {
  name            = "${var.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.desired_count_worker
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.application_sg_id]
    assign_public_ip = false
  }
  service_registries {
    registry_arn = aws_service_discovery_service.internal["worker"].arn
  }
}
resource "aws_ecs_service" "frontend" {
  name            = "${var.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.desired_count_frontend
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.application_sg_id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }
  health_check_grace_period_seconds = 60
  depends_on                        = [aws_lb_listener.http, aws_lb_listener.https]
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}
output "alb_zone_id" {
  value = aws_lb.main.zone_id
}
output "alb_arn_suffix" {
  value = aws_lb.main.arn_suffix
}
output "target_group_arn_suffixes" {
  value = [aws_lb_target_group.backend.arn_suffix, aws_lb_target_group.frontend.arn_suffix]
}
output "cluster_name" {
  value = aws_ecs_cluster.main.name
}
output "backend_service_name" {
  value = aws_ecs_service.backend.name
}
output "worker_service_name" {
  value = aws_ecs_service.worker.name
}
output "frontend_service_name" {
  value = aws_ecs_service.frontend.name
}
output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}
