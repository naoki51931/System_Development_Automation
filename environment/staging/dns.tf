resource "aws_acm_certificate" "staging" {
  count             = var.enable_https && var.create_acm_certificate ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = var.enable_https && var.create_acm_certificate ? {
    for option in aws_acm_certificate.staging[0].domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "staging" {
  count                   = var.enable_https && var.create_acm_certificate ? 1 : 0
  certificate_arn         = aws_acm_certificate.staging[0].arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}

locals {
  effective_acm_certificate_arn = var.enable_https ? (
    var.create_acm_certificate ? aws_acm_certificate_validation.staging[0].certificate_arn : var.acm_certificate_arn
  ) : ""
}

resource "aws_route53_record" "staging" {
  count   = var.enable_https && var.create_route53_record ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.ecs.alb_dns_name
    zone_id                = module.ecs.alb_zone_id
    evaluate_target_health = true
  }
}
