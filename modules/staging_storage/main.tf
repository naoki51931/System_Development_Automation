variable "enabled" {
  type = bool
}
variable "bucket_name" {
  type = string
}
variable "name_prefix" {
  type = string
}
variable "cors_origin" {
  type = string
}

resource "aws_s3_bucket" "main" {
  count  = var.enabled ? 1 : 0
  bucket = var.bucket_name
  lifecycle {
    prevent_destroy = true
  }
}
resource "aws_s3_bucket_versioning" "main" {
  count  = var.enabled ? 1 : 0
  bucket = aws_s3_bucket.main[0].id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  count  = var.enabled ? 1 : 0
  bucket = aws_s3_bucket.main[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_public_access_block" "main" {
  count                   = var.enabled ? 1 : 0
  bucket                  = aws_s3_bucket.main[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  count  = var.enabled ? 1 : 0
  bucket = aws_s3_bucket.main[0].id
  rule {
    id     = "staging-artifact-retention"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

  }
}
resource "aws_s3_bucket_cors_configuration" "main" {
  count  = var.enabled && var.cors_origin != "" ? 1 : 0
  bucket = aws_s3_bucket.main[0].id
  cors_rule {
    allowed_headers = ["Content-Type", "x-amz-content-sha256"]
    allowed_methods = ["GET", "PUT"]
    allowed_origins = [var.cors_origin]
    expose_headers  = ["ETag"]
    max_age_seconds = 300

  }
}
data "aws_iam_policy_document" "tls" {
  count = var.enabled ? 1 : 0
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.main[0].arn, "${aws_s3_bucket.main[0].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }

  }
}
resource "aws_s3_bucket_policy" "tls" {
  count  = var.enabled ? 1 : 0
  bucket = aws_s3_bucket.main[0].id
  policy = data.aws_iam_policy_document.tls[0].json
}
output "bucket_name" {
  value = try(aws_s3_bucket.main[0].bucket, null)
}
output "bucket_arn" {
  value = try(aws_s3_bucket.main[0].arn, null)
}
