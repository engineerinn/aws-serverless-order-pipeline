# AWS Serverless Order Processing Pipeline
> Event-driven, serverless pipeline for processing and analysing e-commerce orders at scale.
Steps.

1. Create / login into AWS account.
2. Create / assign an IAM user for providing credentials to GitHub Actions and Terraform
3.  

![CI](https://github.com/YOUR_USERNAME/aws-order-pipeline/actions/workflows/deploy.yml/badge.svg)

![License](https://img.shields.io/badge/license-MIT-blue.svg)

> Event-driven, serverless pipeline for processing and analysing e-commerce orders at scale.

## Architecture

[architecture diagram here]

## Tech Stack

AWS: S3 · Lambda · Step Functions · DynamoDB · SQS · SNS · EventBridge

     API Gateway · Glue · Athena · CloudWatch · X-Ray · Secrets Manager

IaC: Terraform

CI/CD: GitHub Actions

Language: Python 3.12

## Features

- Validates and enriches CSV order batches on upload

- Orchestrated multi-step workflow with retry and error-catch logic

- Dead Letter Queue for failed messages

- Daily Athena analytics export (partitioned by date)

- REST API with API Key authentication to query orders

- Full observability: CloudWatch dashboard + failure alarms + X-Ray tracing

- Infrastructure fully managed as code (Terraform)

- Tested with pytest + moto; deployed automatically on merge to main

## Getting Started

[deployment instructions...]

## API Reference

[endpoint docs...]

