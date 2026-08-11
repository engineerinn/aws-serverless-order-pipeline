# AWS Serverless Order Processing Pipeline
> Event-driven, serverless pipeline for processing and analysing e-commerce orders at scale.
Steps.

**Project Objective**
[Kasih Penjelasan]

**Deployment Steps**
[Kasih Penjelasan]

1. Create / login into AWS account.
2. Create / assign an IAM user for providing credentials to GitHub Actions and Terraform
3.  

![CI](https://github.com/YOUR_USERNAME/aws-order-pipeline/actions/workflows/deploy.yml/badge.svg)

![License](https://img.shields.io/badge/license-MIT-blue.svg)

> Event-driven, serverless pipeline for processing and analysing e-commerce orders at scale.

## Architecture

[architecture diagram here]

## Tech Stack

**AWS** [Pada setiap AWS produk, harus dikasih penjelasan singkat dan rolenya dalam proyek ini!]
1. S3
2. Lambda
3. Step Functions
4. DynamoDB
5. SQS (Simple Queue Service)
6. SNS (Simple Notification Service)
7. EventBridge
8. API Gateway
9. Glue
10. Athena
11. CloudWatch
12. X-Ray
13. Secrets Manager

**IaC**

Terraform
[kasih penjelasan singkat mengenai Terraform dan perannya dalam proyek ini]

**CI/CD**
GitHub Actions
[kasih penjelasan singkat mengenai GitHub Actions dan perannya dalam proyek ini]

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

