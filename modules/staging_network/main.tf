variable "create_vpc" {
  type = bool
}
variable "name_prefix" {
  type = string
}
variable "vpc_cidr" {
  type = string
}

data "aws_availability_zones" "available" {
  count = var.create_vpc ? 1 : 0
  state = "available"
}

resource "aws_vpc" "main" {
  count                = var.create_vpc ? 1 : 0
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "${var.name_prefix}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  tags = {
    Name = "${var.name_prefix}-igw"
  }
}

resource "aws_subnet" "public" {
  count                   = var.create_vpc ? 2 : 0
  vpc_id                  = aws_vpc.main[0].id
  availability_zone       = data.aws_availability_zones.available[0].names[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch = false
  tags = {
    Name = "${var.name_prefix}-public-${count.index + 1}"
  }
}

resource "aws_subnet" "private" {
  count             = var.create_vpc ? 2 : 0
  vpc_id            = aws_vpc.main[0].id
  availability_zone = data.aws_availability_zones.available[0].names[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  tags = {
    Name = "${var.name_prefix}-private-${count.index + 1}"
  }
}

resource "aws_eip" "nat" {
  count  = var.create_vpc ? 1 : 0
  domain = "vpc"
  tags = {
    Name = "${var.name_prefix}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  count         = var.create_vpc ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
  tags = {
    Name = "${var.name_prefix}-nat"
  }
}

resource "aws_route_table" "public" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }
  tags = {
    Name = "${var.name_prefix}-public-rt"
  }
}

resource "aws_route_table" "private" {
  count  = var.create_vpc ? 1 : 0
  vpc_id = aws_vpc.main[0].id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }
  tags = {
    Name = "${var.name_prefix}-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = var.create_vpc ? 2 : 0
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}
resource "aws_route_table_association" "private" {
  count          = var.create_vpc ? 2 : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

output "vpc_id" {
  value = try(aws_vpc.main[0].id, null)
}
output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}
output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
