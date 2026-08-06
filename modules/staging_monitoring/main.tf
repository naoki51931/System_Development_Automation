variable "name_prefix" {
  type = string
}
variable "cluster_name" {
  type = string
}
variable "backend_service_name" {
  type = string
}
variable "worker_service_name" {
  type = string
}
variable "frontend_service_name" {
  type = string
}
variable "alb_arn_suffix" {
  type = string
}
variable "target_group_arn_suffixes" {
  type = list(string)
}
variable "db_identifier" {
  type = string
}
variable "alarm_notification_email" {
  type      = string
  sensitive = true
}
variable "monthly_budget_amount" {
  type = number
}

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}
resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_notification_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

locals {
  service_dimensions = {
    backend  = var.backend_service_name
    worker   = var.worker_service_name
    frontend = var.frontend_service_name

  }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  for_each            = local.service_dimensions
  alarm_name          = "${var.name_prefix}-${each.key}-cpu"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  dimensions = {
    ClusterName = var.cluster_name, ServiceName = each.value
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  for_each            = local.service_dimensions
  alarm_name          = "${var.name_prefix}-${each.key}-memory"
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  dimensions = {
    ClusterName = var.cluster_name, ServiceName = each.value
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name_prefix}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 2
  period              = 300
  statistic           = "Sum"
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  count               = length(var.target_group_arn_suffixes)
  alarm_name          = "${var.name_prefix}-target-${count.index + 1}-unhealthy"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 2
  period              = 60
  statistic           = "Maximum"
  dimensions = {
    LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffixes[count.index]
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.name_prefix}-rds-connections"
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.name_prefix}-rds-free-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  comparison_operator = "LessThanThreshold"
  threshold           = 5368709120
  evaluation_periods  = 2
  period              = 300
  statistic           = "Minimum"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "worker_heartbeat" {
  alarm_name          = "${var.name_prefix}-worker-heartbeat"
  namespace           = "SystemNavigator/Staging"
  metric_name         = "WorkerHeartbeatAgeSeconds"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 120
  evaluation_periods  = 2
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "breaching"
  dimensions = {
    Environment = "staging"
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "dead_letter" {
  alarm_name          = "${var.name_prefix}-dead-letter-growth"
  namespace           = "SystemNavigator/Staging"
  metric_name         = "DeadLetterCount"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Environment = "staging"
  }
  alarm_actions = local.alarm_actions
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_amount)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Environment$staging"]
  }
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.alerts.arn]

  }
}
