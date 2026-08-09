variable "repository_names" {
  type = set(string)
}
variable "retain_tagged_images" {
  type    = number
  default = 20
}

resource "aws_ecr_repository" "staging" {
  for_each             = var.repository_names
  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "staging" {
  for_each   = aws_ecr_repository.staging
  repository = each.value.name
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
        description  = "Retain the newest reviewed tagged images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = var.retain_tagged_images
        }
        action = { type = "expire" }
      }
    ]
  })
}

output "repository_urls" {
  value = { for name, repository in aws_ecr_repository.staging : name => repository.repository_url }
}
output "repository_arns" {
  value = { for name, repository in aws_ecr_repository.staging : name => repository.arn }
}
