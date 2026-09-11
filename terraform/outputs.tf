output "lambda_url" {
  value = aws_lambda_function_url.app.function_url
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
