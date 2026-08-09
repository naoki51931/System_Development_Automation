locals {
  effective_acm_certificate_arn = var.acm_certificate_arn
}

# Certificate validation belongs to staging-prerequisites. The alias stays here
# because it depends on the ALB managed by this state.
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
