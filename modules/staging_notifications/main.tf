variable "name_prefix" { type = string }
variable "alarm_notification_email" { type = string }
variable "monthly_budget_amount" { type = number }
variable "budget_currency" { type = string }

resource "aws_sns_topic" "alerts" { name = "${var.name_prefix}-alerts" }

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_amount)
  limit_unit   = var.budget_currency
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Environment$staging"]
  }
  dynamic "notification" {
    for_each = {
      actual_50    = { threshold = 50, type = "ACTUAL" }
      actual_80    = { threshold = 80, type = "ACTUAL" }
      actual_100   = { threshold = 100, type = "ACTUAL" }
      forecast_100 = { threshold = 100, type = "FORECASTED" }
    }
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = [var.alarm_notification_email]
    }
  }
}

output "sns_topic_arn" { value = aws_sns_topic.alerts.arn }
output "alert_email_address" { value = var.alarm_notification_email }
output "budget_name" { value = aws_budgets_budget.monthly.name }
