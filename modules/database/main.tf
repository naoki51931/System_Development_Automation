variable "name" { type = string }
variable "instance_class" { type = string }
variable "database_subnet_ids" { type = list(string) }
variable "application_sg_id" { type = string }

data "aws_subnet" "selected" { id = var.database_subnet_ids[0] }

resource "random_password" "db" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "db" {
  name = "${var.name}/database"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = "app_admin"
    password = random_password.db.result
  })
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name}-db"
  subnet_ids = var.database_subnet_ids
}

resource "aws_security_group" "db" {
  name   = "${var.name}-db"
  vpc_id = data.aws_subnet.selected.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.application_sg_id]
  }
}

resource "aws_db_instance" "main" {
  identifier                = "${var.name}-postgres"
  engine                    = "postgres"
  instance_class            = var.instance_class
  allocated_storage         = 50
  storage_encrypted         = true
  username                  = "app_admin"
  password                  = random_password.db.result
  db_subnet_group_name      = aws_db_subnet_group.main.name
  vpc_security_group_ids    = [aws_security_group.db.id]
  publicly_accessible       = false
  multi_az                  = true
  backup_retention_period   = 14
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name}-final"

  lifecycle { prevent_destroy = true }
}

output "secret_arn" {
  value     = aws_secretsmanager_secret.db.arn
  sensitive = true
}
