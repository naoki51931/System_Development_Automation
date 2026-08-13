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
variable "sns_topic_arn" { type = string }
variable "desired_count_backend" {
  type = number
}
variable "desired_count_worker" {
  type = number
}
variable "rds_connections_threshold" {
  type = number
}
variable "rds_free_storage_threshold" {
  type = number
}
variable "rds_freeable_memory_threshold" {
  type = number
}
variable "enable_runtime_services" {
  type        = bool
  description = "Create service and worker-runtime alarms only with runtime services."
  default     = false
}
variable "enabled" {
  type        = bool
  description = "Create infrastructure alarms only in ACTIVE mode."
}

locals {
  service_dimensions = var.enabled && var.enable_runtime_services ? {
    backend  = var.backend_service_name
    worker   = var.worker_service_name
    frontend = var.frontend_service_name

  } : {}
  alarm_actions = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  for_each            = local.service_dimensions
  alarm_name          = "${var.name_prefix}-${each.key}-cpu"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  evaluation_periods  = 1
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
  evaluation_periods  = 1
  period              = 300
  statistic           = "Average"
  dimensions = {
    ClusterName = var.cluster_name, ServiceName = each.value
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count               = var.enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  count               = var.enabled ? length(var.target_group_arn_suffixes) : 0
  alarm_name          = "${var.name_prefix}-target-${count.index + 1}-unhealthy"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  period              = 60
  statistic           = "Maximum"
  dimensions = {
    LoadBalancer = var.alb_arn_suffix, TargetGroup = var.target_group_arn_suffixes[count.index]
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "alb_response_time" {
  count               = var.enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-alb-response-time-p95"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 2
  evaluation_periods  = 5
  period              = 60
  extended_statistic  = "p95"
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "running_tasks" {
  for_each = var.enabled && var.enable_runtime_services ? {
    backend = { service = var.backend_service_name, desired = var.desired_count_backend }
    worker  = { service = var.worker_service_name, desired = var.desired_count_worker }
  } : {}
  alarm_name          = "${var.name_prefix}-${each.key}-running-tasks"
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  comparison_operator = "LessThanThreshold"
  threshold           = each.value.desired
  evaluation_periods  = 1
  period              = 60
  statistic           = "Minimum"
  treat_missing_data  = "breaching"
  dimensions = {
    ClusterName = var.cluster_name, ServiceName = each.value.service
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-rds-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_connections_threshold
  evaluation_periods  = 3
  period              = 300
  statistic           = "Average"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  count               = var.enabled ? 1 : 0
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
  count               = var.enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-rds-free-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  comparison_operator = "LessThanThreshold"
  threshold           = var.rds_free_storage_threshold
  evaluation_periods  = 2
  period              = 300
  statistic           = "Minimum"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "rds_freeable_memory" {
  count               = var.enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-rds-freeable-memory"
  namespace           = "AWS/RDS"
  metric_name         = "FreeableMemory"
  comparison_operator = "LessThanThreshold"
  threshold           = var.rds_freeable_memory_threshold
  evaluation_periods  = 2
  period              = 300
  statistic           = "Minimum"
  dimensions = {
    DBInstanceIdentifier = var.db_identifier
  }
  alarm_actions = local.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "worker_heartbeat" {
  count               = var.enabled && var.enable_runtime_services ? 1 : 0
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
  count               = var.enabled && var.enable_runtime_services ? 1 : 0
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
