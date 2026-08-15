variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "bucket_arn" {
  type = string
}

variable "image_tag" {
  type        = string
  description = "ECSで実行するECRイメージのタグ"
}

variable "app_image" {
  type        = string
  description = "Digest-pinned Production image shared by backend, worker, and migration."
}

variable "frontend_image" {
  type        = string
  description = "Digest-pinned image from the dedicated Production frontend repository."
}

variable "aws_region" { type = string }
variable "database_secret_arn" { type = string }
variable "enable_release_runtime" { type = bool }
variable "release_gate_approved" { type = bool }

variable "capacity_profile" { type = string }
variable "backend_cpu" { type = number }
variable "backend_memory" { type = number }
variable "desired_count" { type = number }
variable "min_count" { type = number }
variable "max_count" { type = number }
variable "cpu_target" { type = number }
variable "memory_target" { type = number }

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.name}-ecr"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.name}-frontend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = "${var.name}-frontend-ecr"
  }
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Remove untagged images after seven days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Retain the newest 20 tagged release images for rollback"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 20
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecs_cluster" "main" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.name}-cluster"
  }
}

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "Allow HTTP traffic to ALB"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-alb-sg"
  }
}

resource "aws_security_group" "app" {
  name        = "${var.name}-app"
  description = "Allow application traffic from ALB"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Application traffic from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Frontend traffic from ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-app-sg"
  }
}

resource "aws_lb" "main" {
  name               = substr(var.name, 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  tags = {
    Name = "${var.name}-alb"
  }
}

resource "aws_lb_target_group" "app" {
  name        = substr("${var.name}-app", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.name}-target-group"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

output "application_sg_id" {
  value = aws_security_group.app.id
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "frontend_ecr_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "release" {
  for_each          = toset(["backend", "frontend", "worker", "migration"])
  name              = "/ecs/${var.name}/${each.key}"
  retention_in_days = 30
}

resource "aws_iam_role" "task_execution" {
  name = "${var.name}-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_secret_arn]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "database-secret-read"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

resource "aws_iam_role" "task" {
  name = "${var.name}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "release_task" {
  for_each = toset(["backend", "frontend", "worker", "migration"])
  name     = "${var.name}-${each.key}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "worker_metrics" {
  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["SystemNavigator/Production"]
    }
  }
}

resource "aws_iam_role_policy" "worker_metrics" {
  name   = "production-worker-metrics"
  role   = aws_iam_role.release_task["worker"].id
  policy = data.aws_iam_policy_document.worker_metrics.json
}

locals {
  production_environment = [
    { name = "APP_ENV", value = "production" },
    { name = "APP_LOCAL_AUTH_ENABLED", value = "false" },
    { name = "APP_ENABLE_MOCK_AI", value = "false" },
    { name = "APP_ENABLE_MOCK_PAYMENT", value = "false" },
    { name = "APP_ENABLE_MOCK_EMAIL", value = "false" },
    { name = "APP_ENABLE_COGNITO", value = "false" },
    { name = "APP_ENABLE_STRIPE", value = "false" },
    { name = "APP_ENABLE_SES", value = "false" }
  ]
  release_gate_valid = !var.enable_release_runtime || var.release_gate_approved
  database_secret = [{
    name      = "APP_DATABASE_SECRET_JSON"
    valueFrom = var.database_secret_arn
  }]
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = "eu-west-2"
          awslogs-stream-prefix = "app"
        }
      }

      environment = [
        {
          name  = "APP_ENV"
          value = "production"
        }
      ]
    }
  ])
}

# Keep the current Production task definition managed and registered for an
# immediate rollback. The reviewed low-traffic profile uses a separate family,
# avoiding replacement/deregistration of the known-good revision.
resource "aws_ecs_task_definition" "app_low_traffic" {
  count                    = var.capacity_profile == "low-traffic" ? 1 : 0
  family                   = "${var.name}-low-traffic"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.backend_cpu)
  memory                   = tostring(var.backend_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions    = aws_ecs_task_definition.app.container_definitions
}

resource "aws_ecs_task_definition" "release_backend" {
  family                   = "${var.name}-release-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.backend_cpu)
  memory                   = tostring(var.backend_memory)
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.release_task["backend"].arn
  container_definitions = jsonencode([{
    name         = "app", image = var.app_image, essential = true,
    command      = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }],
    environment  = local.production_environment, secrets = local.database_secret,
    healthCheck = {
      command  = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"]
      interval = 30, timeout = 5, retries = 3, startPeriod = 20
    },
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group = aws_cloudwatch_log_group.release["backend"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "backend"
    } }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.release_task["worker"].arn
  container_definitions = jsonencode([{
    name    = "worker", image = var.app_image, essential = true,
    command = ["python", "-m", "app.workers.runner"],
    environment = concat(local.production_environment, [
      { name = "APP_WORKER_METRICS_NAMESPACE", value = "SystemNavigator/Production" },
      { name = "APP_WORKER_SERVICE_NAME", value = "${var.name}-worker" }
    ]), secrets = local.database_secret,
    healthCheck = { command = ["CMD-SHELL", "python -m app.workers.health"], interval = 30, timeout = 10, retries = 3 },
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group = aws_cloudwatch_log_group.release["worker"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "worker"
    } }
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.release_task["frontend"].arn
  container_definitions = jsonencode([{
    name         = "frontend", image = var.frontend_image, essential = true,
    command      = ["node", "server.js"],
    portMappings = [{ containerPort = 3000, hostPort = 3000, protocol = "tcp" }],
    environment = [
      { name = "APP_ENV", value = "production" },
      { name = "APP_ENABLE_MOCK_AI", value = "false" },
      { name = "APP_ENABLE_MOCK_PAYMENT", value = "false" },
      { name = "APP_ENABLE_MOCK_EMAIL", value = "false" }
    ],
    healthCheck = { command = ["CMD-SHELL", "wget -q -O /dev/null http://localhost:3000/login || exit 1"], interval = 30, timeout = 5, retries = 3 },
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group = aws_cloudwatch_log_group.release["frontend"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "frontend"
    } }
  }])
}

# Definition only: Terraform never invokes this task. Operators run it as a
# separately approved one-off and attest its exact app digest at the root gate.
resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.release_task["migration"].arn
  container_definitions = jsonencode([{
    name        = "migration", image = var.app_image, essential = true,
    command     = ["alembic", "upgrade", "head"],
    environment = local.production_environment, secrets = local.database_secret,
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group = aws_cloudwatch_log_group.release["migration"].name, awslogs-region = var.aws_region, awslogs-stream-prefix = "migration"
    } }
  }])
}

resource "aws_lb_target_group" "frontend" {
  name        = substr("${var.name}-frontend", 0, 32)
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/login"
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener_rule" "frontend" {
  count        = var.enable_release_runtime ? 1 : 0
  listener_arn = aws_lb_listener.http.arn
  priority     = 50000

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

resource "aws_lb_listener_rule" "backend_api" {
  count        = var.enable_release_runtime ? 1 : 0
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/docs*", "/openapi.json", "/health", "/static/*"]
    }
  }
}

resource "aws_ecs_service" "app" {
  name            = var.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = var.enable_release_runtime ? aws_ecs_task_definition.release_backend.arn : (var.capacity_profile == "low-traffic" ? aws_ecs_task_definition.app_low_traffic[0].arn : aws_ecs_task_definition.app.arn)
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  health_check_grace_period_seconds = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [desired_count]
    precondition {
      condition     = local.release_gate_valid
      error_message = "MIGRATION_SEQUENCE_UNSAFE: verified migration attestation is required before backend digest rollout."
    }
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.task_execution
  ]
}

resource "aws_ecs_service" "worker" {
  count           = var.enable_release_runtime ? 1 : 0
  name            = "${var.name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  lifecycle {
    precondition {
      condition     = local.release_gate_valid
      error_message = "MIGRATION_SEQUENCE_UNSAFE: verified migration attestation is required before worker rollout."
    }
  }
}

resource "aws_ecs_service" "frontend" {
  count           = var.enable_release_runtime ? 1 : 0
  name            = "${var.name}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener_rule.frontend]
  lifecycle {
    precondition {
      condition     = local.release_gate_valid
      error_message = "MIGRATION_SEQUENCE_UNSAFE: verified migration attestation is required before frontend rollout."
    }
  }
}

resource "aws_appautoscaling_target" "app" {
  max_capacity       = var.max_count
  min_capacity       = var.min_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.app.resource_id
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  service_namespace  = aws_appautoscaling_target.app.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.cpu_target
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "memory" {
  name               = "${var.name}-memory-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.app.resource_id
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  service_namespace  = aws_appautoscaling_target.app.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.memory_target
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
  }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "alb_arn_suffix" {
  value = aws_lb.main.arn_suffix
}

output "target_group_arn_suffix" {
  value = aws_lb_target_group.app.arn_suffix
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.app.arn
}

output "task_execution_role_arn" {
  value = aws_iam_role.task_execution.arn
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "frontend_service_name" { value = try(aws_ecs_service.frontend[0].name, "${var.name}-frontend") }
output "worker_service_name" { value = try(aws_ecs_service.worker[0].name, "${var.name}-worker") }
output "release_task_definition_arns" {
  value = {
    backend   = aws_ecs_task_definition.release_backend.arn
    frontend  = aws_ecs_task_definition.frontend.arn
    worker    = aws_ecs_task_definition.worker.arn
    migration = aws_ecs_task_definition.migration.arn
  }
}
output "release_runtime_enabled" { value = var.enable_release_runtime }
