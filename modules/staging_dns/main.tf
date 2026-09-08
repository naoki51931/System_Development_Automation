variable "domain_name" { type = string }
variable "dns_provider" {
  type = string
  validation {
    condition     = contains(["external", "route53"], var.dns_provider)
    error_message = "dns_provider must be external or route53."
  }
}
variable "route53_zone_id" {
  type    = string
  default = ""
}

resource "aws_acm_certificate" "staging" {
  domain_name       = var.domain_name
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "validation" {
  for_each = var.dns_provider == "route53" ? {
    for option in aws_acm_certificate.staging.domain_validation_options : option.domain_name => {
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
  count                   = var.dns_provider == "route53" ? 1 : 0
  certificate_arn         = aws_acm_certificate.staging.arn
  validation_record_fqdns = [for record in aws_route53_record.validation : record.fqdn]
}

output "certificate_arn" { value = aws_acm_certificate.staging.arn }
output "validation_records" {
  description = "DNS records to copy into the authoritative DNS provider."
  value = [
    for option in aws_acm_certificate.staging.domain_validation_options : {
      domain = option.domain_name
      name   = option.resource_record_name
      type   = option.resource_record_type
      value  = option.resource_record_value
    }
  ]
}
