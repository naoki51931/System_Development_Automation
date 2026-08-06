variable "name_prefix" {
  type = string
}
variable "identifier" {
  type = string
}
variable "vpc_id" {
  type = string
}
variable "subnet_ids" {
  type = list(string)
}
variable "application_sg_id" {
  type = string
}
variable "instance_class" {
  type = string
}
variable "multi_az" {
  type = bool
}
variable "backup_retention_days" {
  type = number
}
variable "deletion_protection" {
  type = bool
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.subnet_ids
}
resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db"
  description = "PostgreSQL from staging application tasks only"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.application_sg_id]

  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_db_instance" "main" {
  identifier                      = var.identifier
  engine                          = "postgres"
  engine_version                  = "17"
  instance_class                  = var.instance_class
  allocated_storage               = 30
  max_allocated_storage           = 100
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "systemnavigator"
  username                        = "staging_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.db.id]
  publicly_accessible             = false
  multi_az                        = var.multi_az
  backup_retention_period         = var.backup_retention_days
  deletion_protection             = var.deletion_protection
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${var.identifier}-final"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  auto_minor_version_upgrade      = true
  copy_tags_to_snapshot           = true
  lifecycle {
    prevent_destroy = true
  }
}
output "identifier" {
  value = aws_db_instance.main.identifier
}
output "secret_arn" {
  value     = aws_db_instance.main.master_user_secret[0].secret_arn
  sensitive = true
}
