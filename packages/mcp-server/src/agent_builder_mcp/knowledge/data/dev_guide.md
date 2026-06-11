# AWS Transform Agent Developer Guide (v0.3)

> **Note:** This guide is auto-formatted from the source document. Section numbers in cross-references refer to the headings below.

## Table of Contents

- [Introduction](#introduction)
  - [Change Log](#change-log)
- [System Architecture and Workflow](#system-architecture-and-workflow)
  - [AWS Transform Architecture](#aws-transform-architecture)
  - [Partner Agent Onboarding Architecture](#partner-agent-onboarding-architecture)
  - [Third Party Agent Invocation Flow](#third-party-agent-invocation-flow)
  - [Customer Interaction - Chat flow](#customer-interaction---chat-flow)
  - [Agent Lifecycle Management](#agent-lifecycle-management)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Setting Up Your Development Environment](#setting-up-your-development-environment)
- [Building Your Agent](#building-your-agent)
  - [Low Code](#low-code)
    - [Custom Agent Implementation](#custom-agent-implementation)
      - [Default Orchestrator Agent Example](#default-orchestrator-agent-example)
      - [Default Task Agent Example](#default-task-agent-example)
      - [Default Orchestrator Agent with Task Agent Example](#default-orchestrator-agent-with-task-agent-example)
  - [Build Container](#build-container)
- [Developer Testing](#developer-testing)
  - [Developer Local Testing](#developer-local-testing)
    - [Local Testing IAM Permissions](#local-testing-iam-permissions)
    - [Local Testing Environment Variables](#local-testing-environment-variables)
    - [Build and Publish Agent Docker Image](#build-and-publish-agent-docker-image)
      - [AWS CLI](#aws-cli)
      - [Test message/send](#test-messagesend)
- [Onboarding and Production Webapp Testing](#onboarding-and-production-webapp-testing)
  - [Update local agent container into ECR](#update-local-agent-container-into-ecr)
  - [Deploy your ECR container with Bedrock AgentCore](#deploy-your-ecr-container-with-bedrock-agentcore)
    - [Create AgentCoreExecutionRole](#create-agentcoreexecutionrole)
    - [Create Bedrock AgentCore Runtime](#create-bedrock-agentcore-runtime)
  - [Register Agent with AWS Transform](#register-agent-with-aws-transform)
    - [Publish An Agent Version](#publish-an-agent-version)
    - [Configure Access Control](#configure-access-control)
    - [Agent Management and Monitoring](#agent-management-and-monitoring)
      - [List Your Published Agents](#list-your-published-agents)
      - [Get Agent Details](#get-agent-details)
  - [AWS Transform Prod WebApp testing](#aws-transform-prod-webapp-testing)
  - [External Agentic API support [To Be released]](#external-agentic-api-support-to-be-released)
  - [Publish Agent to be consumed in customer account [WIP]](#publish-agent-to-be-consumed-in-customer-account-wip)
- [FAQ](#faq)
  - [AWS Transform Concepts FAQs](#aws-transform-concepts-faqs)
    - [What is job plan of an AWS Transform job?](#what-is-job-plan-of-an-aws-transform-job)
    - [How is a job plan typically created?](#how-is-a-job-plan-typically-created)
  - [AWS Transform Agent FAQs](#aws-transform-agent-faqs)
    - [What is the minimum requirement for an agent to be an AWS Transform agent?](#what-is-the-minimum-requirement-for-an-agent-to-be-an-aws-transform-agent)
    - [Do I have to use AWS Transform provided base agent to build my agent?](#do-i-have-to-use-aws-transform-provided-base-agent-to-build-my-agent)
    - [May I use langgraph to build my agent instead of strands agent?](#may-i-use-langgraph-to-build-my-agent-instead-of-strands-agent)
    - [How the orchestrator agent select subagents?](#how-the-orchestrator-agent-select-subagents)
    - [What's the difference between BaseAgent AgentRuntimeServer and the traditional CLI approach?](#whats-the-difference-between-baseagent-agentruntimeserver-and-the-traditional-cli-approach)
  - [HITL (Human-in-the-Loop) Task FAQs](#hitl-human-in-the-loop-task-faqs)
    - [What are HITL (Human-in-the-Loop) Tasks?](#what-are-hitl-human-in-the-loop-tasks)
    - [HITL (Human-in-the-Loop) blocking vs non-blocking](#hitl-human-in-the-loop-blocking-vs-non-blocking)
    - [Standard vs critical HITL (Human-in-the-Loop) task](#standard-vs-critical-hitl-human-in-the-loop-task)
    - [What are the available HITL (Human-in-the-Loop) UI for Agent?](#what-are-the-available-hitl-human-in-the-loop-ui-for-agent)
- [Troubleshooting](#troubleshooting)
  - [Troubleshoot Local Testing - SSL: CERTIFICATE_VERIFY_FAILED Error with Boto3](#troubleshoot-local-testing---ssl-certificate_verify_failed-error-with-boto3)
    - [Symptom](#symptom)
    - [Root Cause](#root-cause)
    - [Solution 1: Use a Combined CA Bundle](#solution-1-use-a-combined-ca-bundle)
    - [Solution 2: Use proxy_ca_bundle in Config](#solution-2-use-proxy_ca_bundle-in-config)
    - [Solution 3: Temporarily Disable SSL Verification (Local Testing Only)](#solution-3-temporarily-disable-ssl-verification-local-testing-only)
    - [Symptom](#symptom)
    - [Step 2: Validate general payload structure](#step-2-validate-general-payload-structure)
    - [Step 3: Validate AWS Transform specific payload structure](#step-3-validate-aws-transform-specific-payload-structure)
  - [Troubleshooting "Either endpoint_url or both stage and region must be provided" in Bedrock AgentCore](#troubleshooting-either-endpoint_url-or-both-stage-and-region-must-be-provided-in-bedrock-agentcore)
    - [Solution: Update the runtime environment variables](#solution-update-the-runtime-environment-variables)
- [Appendix](#appendix)
  - [Base Agent Code Walkthrough](#base-agent-code-walkthrough)
    - [What This Package Provides](#what-this-package-provides)
    - [Core Architecture](#core-architecture)
    - [Understanding Agents and Entry Points](#understanding-agents-and-entry-points)
      - [What is an Agent?](#what-is-an-agent)
      - [What is an Entry Point?](#what-is-an-entry-point)
    - [Runtime Architecture](#runtime-architecture)
      - [Orchestrator Runtime Architecture](#orchestrator-runtime-architecture)
      - [Subagent Architecture](#subagent-architecture)
    - [Building Orchestrator Agents](#building-orchestrator-agents)
      - [Create Your Orchestrator Class](#create-your-orchestrator-class)
      - [Create Custom Tools (Optional)](#create-custom-tools-optional)
      - [Create Your Entry Point - Old CLI Approach](#create-your-entry-point---old-cli-approach)
      - [Local Testing](#local-testing)
    - [Building Subagents](#building-subagents)
      - [Create Your Subagent Class](#create-your-subagent-class)
      - [Create Custom Tools (Optional)](#create-custom-tools-optional)
      - [Create Your Entry Point](#create-your-entry-point)
      - [Local Testing](#local-testing)
    - [API Reference](#api-reference)
      - [HTTP Endpoints](#http-endpoints)
      - [Notifications Handler (/invocations)](#notifications-handler-invocations)
      - [Checkpointing Functionality](#checkpointing-functionality)
        - [When to Use Each Strategy](#when-to-use-each-strategy)
        - [Components](#components)
        - [Usage](#usage)
    - [Configuration](#configuration)
      - [Required Environment Variables](#required-environment-variables)
      - [Optional Environment Variables](#optional-environment-variables)
      - [Bedrock Guardrails](#bedrock-guardrails)
      - [Available Tools & Integrations](#available-tools-integrations)
  - [AWS Transform Agentic API Specification](#aws-transform-agentic-api-specification)
    - [Common Error Responses](#common-error-responses)
    - [Data Types and Constraints](#data-types-and-constraints)
      - [RequestContext](#requestcontext)
      - [JobMetadata](#jobmetadata)
    - [Common Patterns](#common-patterns)
      - [Pagination](#pagination)
      - [Idempotency](#idempotency)
      - [Sensitive Data](#sensitive-data)
    - [InvokeAgent](#invokeagent)
    - [StopAgent](#stopagent)
    - [ListAgentInstances](#listagentinstances)
    - [GetAgentInstance](#getagentinstance)
    - [UpdateAgentInstance](#updateagentinstance)
    - [ListArtifacts](#listartifacts)
    - [CreateArtifactUploadUrl](#createartifactuploadurl)
    - [CreateArtifactDownloadUrl](#createartifactdownloadurl)
    - [CompleteArtifactUpload](#completeartifactupload)
    - [GetArtifactMetadata](#getartifactmetadata)
    - [CopyArtifact](#copyartifact)
    - [GetJob](#getjob)
    - [UpdateJobStatus](#updatejobstatus)
    - [PutJobPlan](#putjobplan)
    - [ListJobPlanSteps](#listjobplansteps)
    - [UpdateJobPlanStep](#updatejobplanstep)
    - [DeleteJobPlanStep](#deletejobplanstep)
    - [CreateHitlTask](#createhitltask)
    - [ListHitlTasks](#listhitltasks)
    - [GetHitlTask](#gethitltask)
    - [StartHitlTask](#starthitltask)
    - [CloseHitlTask](#closehitltask)
    - [ListConnectors](#listconnectors)
    - [GetConnector](#getconnector)
    - [GetTemporaryCredentialsForConnector](#gettemporarycredentialsforconnector)
    - [RefreshAuthToken](#refreshauthtoken)
    - [SendMessage](#sendmessage)
    - [CreateWorklog](#createworklog)
    - [TestOperation](#testoperation)
    - [PreProdTestOperation](#preprodtestoperation)
  - [AWS Transform Agent Registry External API Specification](#aws-transform-agent-registry-external-api-specification)
    - [Common Error Responses](#common-error-responses)
    - [Data Types and Constraints](#data-types-and-constraints)
      - [RegisterAgentMetadata](#registeragentmetadata)
      - [OwnerType](#ownertype)
      - [AgentConfiguration](#agentconfiguration)
      - [ComputeConfiguration](#computeconfiguration)
      - [MonitoringType](#monitoringtype)
      - [NotificationStatus](#notificationstatus)
      - [AgentVisibility](#agentvisibility)
      - [VersionStatus](#versionstatus)
      - [AccessControl](#accesscontrol)
      - [ProvisionedComputeConfiguration](#provisionedcomputeconfiguration)
      - [LegacyComputeConfiguration](#legacycomputeconfiguration)
      - [RegisterAgentMetadata](#registeragentmetadata)
      - [AgentType](#agenttype)
      - [MDEConfiguration](#mdeconfiguration)
      - [AgentCoreConfiguration](#agentcoreconfiguration)
      - [AgentResiliencyConfiguration](#agentresiliencyconfiguration)
      - [AgentRecoveryConfiguration](#agentrecoveryconfiguration)
    - [Common Patterns](#common-patterns)
      - [Pagination](#pagination)
      - [Idempotency](#idempotency)
    - [GetAgent](#getagent)
    - [GetAgentVersion](#getagentversion)
    - [RegisterAgent](#registeragent)
    - [PublishAgentVersion](#publishagentversion)
    - [ListAgentAccessControl](#listagentaccesscontrol)
    - [UpdatePublisherAccessControl](#updatepublisheraccesscontrol)
  - [HITL Component Input, Output, and Picture Example](#hitl-component-input-output-and-picture-example)
    - [Text Input component](#text-input-component)
    - [Auto Form component](#auto-form-component)
    - [File Upload component](#file-upload-component)
    - [Table component](#table-component)
    - [General Connector component](#general-connector-component)
    - [Markdown Renderer component](#markdown-renderer-component)
- [Reference](#reference)

# Introduction

This document is designed to provide you with a high level and step-by-step roadmap for building, testing, and successfully onboarding your agent with AWS Transform. Whether you are an internal partner or an external partner, this guide will walk you through the entire agent lifecycle, from the initial concept to a fully deployed live agent.

## Change Log

- v0.3 (2025-11-13)
- Major update enabling registering/publishing/developing agents using production AWS Transform APIs and webapp under beta preview
- Please follow section 7 - Onboarding and Production Webapp Testing
- v0.2.2 (2025-11-04)
- Added missing Step to call CompleteArtifactUpload in section 6.3
- v0.2.1 (2025-10-30)
- Fixed the incorrect IAM policies in section 6.1.3
- v0.2.0 (2025-10-25)
- Updated agent registration process in section 6.1
- Updated IAM permission needed for ListAgentByPublisher API
- Updated Agent Registration process to reflect API updates on 10/24
- Updated Agent Registry specification in section 9.3
- v0.1.9 (2025-10-13): Added section 8.3 to troubleshoot "Either endpoint_url or both stage and region must be provided"
- v0.1.8 (2025-09-30)
- Updated section 9.1 Base Agent Code Walkthrough with latest base agent code features including async agent runtime servers
- Added section 9.1.6 of building subagents with BaseAgent
- Added section 9.1.7.3 of using check-pointing feature provided from base agent
- v0.1.7 (2025-09-26)
- Added a sub section 6.1.1 describing the IAM permissions needed for interacting with AWS Transform Agent Registry.
- v0.1.6 (2025-09-21):

Added new section 8.2 Troubleshooting Bedrock AgentCore Testing - 422 Unprocessable Entity Error

- v0.1.5 (2025-09-18):
- Added new section 6.2 Test new job without WebApp
- v0.1.4 (2025-09-16):
- Added new section 6.1.4 Allow AWS Transform Test account to use the agent (Orchestrator Agent Only)
- Improved the script and fixed bugs in section 6.1
- Added new section 7.3 clarifying Human-In-The-Loop tasks
- Added new section 9.4 HITL Component Input, Output, and Picture Example
- v0.1.3 (2025-09-14):

Added new Section 5.2: Bedrock AgentCore Deployed Agent Testing

- Added detailed instructions for building and publishing agent Docker images

Added guide for creating Bedrock AgentCore execution role

Added steps for creating and invoking Bedrock AgentCore runtime

- Added testing procedures for additional operations including message/send
- Added new Section 6.1: Register Agent Core Agent with AWS Transform
- Added configuration steps for AWS Transform Agent Registry CLI
- Added detailed steps for registering agents with AWS Transform
- Added instructions for publishing agent versions
- Added preparation guidelines for AWS Transform Webapp testing

Updated section 4 reflecting latest SDK code updates

- v0.1.2 (2025-09-13):
- Added new Section 9.3: AWS Transform Agent Registry External API Specification
- Added comprehensive API documentation including:
- Common error responses
- Data types and constraints
- Common patterns for pagination and idempotency
- Detailed API operations (GetAgent, RegisterAgent, PublishAgentVersion, etc.)
- Access control operations
- v0.1.1 (2025-09-10):
- Added new Section 8.1: Comprehensive troubleshooting guide for SSL certificate verification failures during local testing
- Added three solution approaches for SSL certificate issues:
- Combined CA Bundle implementation
- Proxy CA bundle configuration
- Temporary SSL verification disable option for local testing only
- Enhanced developer testing documentation with SSL error handling
- v0.1.0.1 (2025-09-07):

Enhanced Bedrock AgentCore Integration Documentation:

Added new subsection 4.1.1 on using AgentRuntimeServer with Bedrock AgentCore

- Added new subsection 4.1.2 for custom agent implementation guidance

Added new subsection 4.2.1 covering Bedrock AgentCore container requirements and Dockerfile

Enhanced Bedrock AgentCore Registration:

- Updated sections 6.2.1-6.2.3 with JSON-RPC protocol explanations

Added detailed Bedrock AgentCore entry point implementation in section 8.1.5.3

Added New FAQ Entries: Added sections 7.2.5-7.2.6 covering Bedrock AgentCore-specific questions

- Improved Documentation: Enhanced code snippet formatting and styling
- v0.1.0 (Initial Release):
- Initial documentation structure and content
- Base AWS Transform architecture overview
- System workflow descriptions
- Basic agent development guidelines
- Initial API specifications
- Core testing procedures
- Development environment setup instructions

# System Architecture and Workflow

## AWS Transform Architecture

![AWS Transform Architecture diagram](media/image1.svg)

AWS Transform provides two types of interfaces: WebApp-facing APIs for WebApp user access and partner agent-facing APIs for partner agents. The WebApp-facing APIs are accessed through the AWS Transform frontend service, and user roles are used to control access and permissions at workspace level. In contrast, partner agents are authorized through tokens that the AWS Transform generates and sends when an agent is invoked. This authorization token is generated at certain workspace and job context. Agent-facing APIs are also provided as a MCP server as one of AWS Transform primitives we offered to partners.

Agents including AWS Transform chat agent, partner domain orchestrator agent and subagents can communicate with each other through A2A message over AWS Transform messaging API. AWS Transform chat agent usually communicates with subagents through an orchestrator agent.

![AWS Transform Architecture diagram](media/image2.svg)

## Partner Agent Onboarding Architecture

- Developer local development environment is Linux or Mac.
- Bedrock AgentCore container accepted Docker runtime is linux/arm64

![Partner Agent Onboarding Architecture diagram](media/image3.svg)

Partner knowledge base onboarding process is similar to this.

## Third Party Agent Invocation Flow

The overall flow for 3rd party agent invocation works as follow as in the below diagram,

- Customer creates a job through AWS Transform Chat, AWS Transform starts processing the job;
- AWS Transform invokes Orchestrator Agent in Partner's account. Orchestrator Agent starts job execution;
- Orchestrator Agent makes AWS Transform API requests (or via MCP) to invoke AWS Transform vended Task Agent;
- AWS Transform invokes AWS Transform vended Task Agent in AWS, which starts processing;
- Orchestrator Agent invokes Partner Task Agent via AWS Transform;
- AWS Transform indicates the job completion to Customer.

This flow demonstrates the high-level composability of agents in Partner AWS account and in AWS Transform service, certain details such as running agents in Bedrock AgentCore will be revealed in subsequent sections, though the overall flow stays as the same.

![Figure. 3rd Party Agent Invocation Flow (the example showing partner composing their Task Agent with an existing Task Agent vended by AWS Transform, via an partner developed Orchestrator Agent)](media/image4.svg)

*Figure. 3rd Party Agent Invocation Flow (the example showing partner composing their Task Agent with an existing Task Agent vended by AWS Transform, via an partner developed Orchestrator Agent)*

## Customer Interaction - Chat flow

Previous section described the invocation flow of multiple agents, with same example, below the diagram describes the high-level Chat interaction flow among customer and agents via AWS Transform:

- Customer requests AWS Transform Chat for their transformation needs in natural language;
- AWS Transform transfers the customer question to Orchestrator Agent in Partner account;
- Orchestrator Agent requests information from AWS Transform vended Task Agent through AWS Transform;
- AWS Transform vended Task Agent responds, then AWS Transform transfers the details to Orchestrator Agent;
- Orchestrator Agent requests additional information from Task Agent running in Partner account;
- Partner Task Agent responds, then AWS Transform transfers the details to Orchestrator Agent;
- Orchestrator Agent combines outputs from both Task Agents and returns to AWS Transform;
- AWS Transform returns the requested the result through AWS Transform Chat to Customer.

In this diagram, agents communicate with each other using Agent2Agent Protocol (A2A) powered by AWS Transform service; agents may communicate using additional mechanisms such as AWS Transform provided Artifact Store API etc., which will be revealed in further details in this guide.

![Figure. 3rd Party Agent Customer Interaction Flow (the example showing customer interacting with two Task Agent, one AWS Transform Task Agent and one Partner Task Agent; customer request is routed to Orchestrator Agent and communicated enabled by AWS Transform service provided A2A )](media/image5.svg)

*Figure. 3rd Party Agent Customer Interaction Flow (the example showing customer interacting with two Task Agent, one AWS Transform Task Agent and one Partner Task Agent; customer request is routed to Orchestrator Agent and communicated enabled by AWS Transform service provided A2A )*

## Agent Lifecycle Management

To be deployed into production, an agent goes through a series of stages. First, a partner agent builder performs local development, building, and testing. Once ready, the agent is uploaded to Elastic Container Registry (ECR) and deployed with Bedrock AgentCore. The agent is then registered with the AWS Transform agentic registry, making it ready to be used for jobs created by the AWS Transform.

- The partner agent builder sets up the local agent development environment.
- The agent builder downloads the AWS Transform base agent to use as a starting point.
- The agent builder customizes and writes the agent code.
- The agent is built locally into a container.

The agent is run locally for development testing by providing it with an API key to access the dev testing AWS Transform endpoint.

- Once local development testing is complete, the agent builder can rebuild the agent with the platform as ARM64 for Bedrock AgentCore.
- The agent builder tags the container image and uploads it to the partner account ECR container repository.
- The agent builder registers their ECR agent container with the agent core using the AWS console, CLI, SDK, or API.
- The agent builder then registers the Bedrock AgentCore runtime to the AWS Transform agent registry by providing an agent card, role, and ARN.

The AWS Transform will trigger the agent when a job is created in the AWS Transform WebApp that can be served by this agent.

- The agent will run in the partner Bedrock AgentCore runtime.
- Partners can monitor and debug the agent through CloudWatch logs.

![Agent Lifecycle Management diagram](media/image6.svg)

![Agent Lifecycle Management diagram](media/image7.svg)

# Getting Started

## Prerequisites

- At least one AWS account with credential setup to access the account through AWS CLI or console
- Work with AWS Transform foundation team to
- allow-list the account for AWS Transform service
- get an API key, testing workspace and job ID for agent development testing

## Setting Up Your Development Environment

- Python 3.10 and above
- IDE - Intellij/PyCharm/VS Code
- Docker

```bash
# Debian distribution
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# RPM distribution
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

- AWS CLI

```
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
snap install aws-cli --classic
```

- awscurl

```bash
pip install awscurl
```

AWS Transform base agent package (including Bedrock AgentCore SDK, Strands Agent SDK and AWS Transform service primitives as MCP server). Install from PyPI:

```bash
pip install agent-builder-sdk-aws-transform agent-builder-mcp-runtime-aws-transform
```

# Building Your Agent

## Low Code

You can use the agent-builder-sdk-aws-transform package to build your agent. Install via pip (see prerequisites above). Below are the steps:

- Create a Python project in your development environment
- Take base agent package as a dependent package
- Define a domain agent class, which extends the base agent
- Create a LLM system prompt for the domain agent
- Create StrandsAgent compatible tool functions
- Specify the local and remote MCP servers
- Optionally, you can specify a list of subagents that can be used by one orchestrator agent
- Extend the agent implementation by customizing the API endpoints the agent supports:
- POST /invocations
- GET /ping
- POST /message/send
- Get the input parameters through /invocations message.

```
### Using AWS Transform Base Agent with Bedrock AgentCore (Recommended)
```

For partners deploying to AWS Bedrock AgentCore, the base agent package provides AgentRuntimeServer that handles all Bedrock AgentCore integration automatically:

Key Benefits:

JSON-RPC 2.0 Protocol: Automatic handling of Bedrock AgentCore's single /invocations endpoint

- Context Initialization: Automatic extraction of AWS Transform context from any request type

Session Management: Built-in support for Bedrock AgentCore's session isolation

- A2A Compatibility: Native support for Agent-to-Agent messaging

```python
# simple_cli_agent_core.py
import argparse
import logging
from agent_builder_sdk.agent_factory import create_default_orchestrator_with_subagent
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.utils import get_prompt_with_name
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(description="Run Agent Runtime Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind server to")
    parser.add_argument(
        "--queue-storage-path",
        default="/tmp/agent_queue",
        help="Path to store request queue and response data",
    )
    parser.add_argument(
        "--storage-dir", default="/tmp/orchestrator_agent", help="Storage directory for agent data"
    )
    parser.add_argument(
        "--binary-location",
        default="/home/amazon/AgentBuilderAgenticMCP/bin/agent-builder-agentic-mcp",
        help="Path to the agentic MCP server binary",
    )
    return parser
def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    # Create agent factory with default configuration
    def agent_factory(mcp_client, storage_dir):
        return create_default_orchestrator_with_subagent(
            mcp_client=mcp_client,
            storage_dir=storage_dir,
            # Pass in your system prompt here
            system_prompt=get_prompt_with_name("test_orchestrator_prompt"),
        )
    logger.info("Starting Agent Runtime Server...")
    server = AgentRuntimeServer(
        agent_factory=agent_factory,
        host=args.host,
        port=args.port,
        queue_storage_path=args.queue_storage_path,
        binary_location=args.binary_location,
        storage_dir=args.storage_dir,
    )
    # This will set up everything and run the server
    server.start()
if __name__ == "__main__":
    main()
```

### Custom Agent Implementation

Above code uses out-of-box default factories to construct agents, you may modify them to customize your agent, or even create your own agent factory implementation for even more control.

#### Default Orchestrator Agent Example

As an example, the default factory creates a fully-featured orchestrator with:

- Episodic memory for storing agent experiences
- Conversation tracking across multiple sources
- Lifecycle hooks for conversation and memory events

You may customize it plugging additional MCP clients for your MCP servers, or bringing additional domain specify tools as custom tools.

```python
def create_default_orchestrator(
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
    system_prompt: Optional[str] = None,
) -> BaseOrchestrator:
...
    # Create orchestrator with explicit hooks
    orchestrator = BaseOrchestrator(
        system_prompt=system_prompt,
        hooks=hooks,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=os.getenv("AWS_REGION") or "us-east-1",
        custom_tools=memory_tools,
    )
    return orchestrator
```

#### Default Task Agent Example

As an example for task agent (sub agent), this factory creates a lightweight subagent without memory or conversation tracking.

Similarly, you may plug-in your domain or business logic centric MCP server or LLM tools to customize a task agent to be an domain task executor.

```python
def create_default_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
) -> BaseSubagent:
...
    # Create subagent with minimal configuration
    subagent = BaseSubagent(
        system_prompt=system_prompt,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=os.getenv("AWS_REGION") or "us-east-1",
    )
    return subagent
```

#### Default Orchestrator Agent with Task Agent Example

One may also choose to leverage multi-agents architecture to run agentic workflow with AWS Transform, below is an example of an orchestrator agent capable of communicating via task agent using A2A.

Note that, the task agent is made visible to the orchestrator agent via the subagent registry tool, and can be tasked with work via send message tool so that it may receive natural language communication from orchestrator agent via A2A.

```python
def create_default_orchestrator_with_subagent(
    system_prompt: str,
    mcp_client: Optional[MCPClient] = None,
    storage_dir: str = "/tmp/orchestrator_agent",
) -> BaseOrchestrator:
    # Create subagent discovery tool
    subagent_registry_tools = SubagentRegistryTools()
    custom_tools.append(subagent_registry_tools.discover_subagents)
    # Create send message to subagent tool
    send_message_tools = SendMessageTools()
    custom_tools.append(send_message_tools.send_message_to_subagent)
...
    # Create orchestrator with explicit hooks
    orchestrator = BaseOrchestrator(
        system_prompt=system_prompt,
        hooks=hooks,
        mcp_clients=[mcp_client] if mcp_client is not None else None,
        region_name=os.getenv("AWS_REGION") or "us-east-1",
        custom_tools=custom_tools,
    )
    return orchestrator
```

## Build Container

- Create a requirements.txt file to include all the dependencies

```bash
# cat requirements.txt
boto3==1.40.12
botocore==1.40.12
fastapi==0.116.1
mcp==1.13.0
strands-agents
uvicorn==0.35.0
uv
requests
```

- Create a Dockerfile to bring everything together

```bash
# cat Dockerfile
FROM python:3.10-slim-buster
```

WORKDIR /app

COPY requirements.txt . RUN pip install --no-cache-dir -r requirements.txt

```
# Copy the agent code into the container
COPY . /app
```

EXPOSE 8000

CMD ["python3", "app.py"]

- Docker build to get a local Docker image. If the local machine is Mac, use platform linux/arm64, if intel or amd based, please use --platform linux/amd64.

```bash
docker build --platform linux/arm64 -t my-agent:latest -f Dockerfile .
```

- (Optionally) Package and deploy to Bedrock AgentCore leveraging out-of-box bedrock-agentcore-starter-toolkit (https://github.com/aws/bedrock-agentcore-starter-toolkit)

```bash
pip install bedrock-agentcore-starter-toolkit
# Configure and deploy (auto-creates all required resources
# including Dockerfile and building Docker image)
agentcore configure -e my_atx_agent.py
agentcore launch
# Test your deployed agent agentcore invoke '{"prompt": "tell me a joke"}'
```

# Developer Testing

Before onboarding your agents with AWS Transform, it is better to perform some local developer testing to identify the potential bugs and problems. Generally, there's three stages of testing you may perform:

- Developer Local Testing

Bedrock AgentCore Deployed Agent Testing

- Testing with AWS Transform Web

This section covers 1 and 2, where 3 requires registering your Bedrock AgentCore ready agents with AWS Transform first.

## Developer Local Testing

### Local Testing IAM Permissions

Before you start testing, here is the minimal permission you need to run the agent locally and the default bedrock model. You can use other models as long as you enable them from Bedrock console.

```json
Minimal IAM user/role policy:
{
   "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "bedrockModelPolicy",
            "Effect": "Allow",
            "Action": "bedrock:InvokeModelWithResponseStream",
            "Resource": "*"
        },
        {
            "Sid": "TransformAgentsApiPolicy",
            "Effect": "Allow",
            "Action": [
                "transform-agents:*"
            ],
            "Resource": "*"
        }
    ]
}
```

Default Bedrock Model: us.anthropic.claude-sonnet-4-5-20250929-v1:0

IMPORTANT: Always use cross-region inference profile IDs (prefixed with "us.") instead of raw model IDs when calling Bedrock. Raw model IDs like "anthropic.claude-sonnet-4-5-20250929-v1:0" will fail with "Invocation with on-demand throughput isn't supported". Use "us.anthropic.claude-sonnet-4-5-20250929-v1:0" instead.

NOTE: When adding permissions for transform-agents using the IAM console, it may show an Error indicating Invalid Service in Action (sample image below). This is because the service is not yet a public AWS Service. This is not a blocker, and clicking the Next should create the IAM policy.

![IAM console "Invalid Service In Action" policy validation warning for transform-agents](media/image8.svg)

IAM Console Error

### Local Testing Environment Variables

Here are the environment variables before running the agent locally, ask your associated SA to get the auth token via AWS Secrets Manager.

```bash
export AWS_ACCESS_KEY_ID=<your-role-user-access-key>
export AWS_SECRET_ACCESS_KEY=<your-role-user-secret-access-key>
export AWS_SESSION_TOKEN=<your-role-user-session-token-key> (ignore this if you use IAM user to test)
export WORKSPACE_ID=<from-secrets-manager>
export JOB_ID=<from-secrets-manager>
export AGENT_INSTANCE_ID=<from-secrets-manager>
export AUTHORIZATION_TOKEN=<from-secrets-manager>
export AWS_REGION=us-east-1
export STAGE=prod
```

- Domain agent can be invoked locally as a Docker container
- Workspace Id and job Id can be passed into the agent through environment variable or invocations message or send message A2A message.
- Agents can use the API key to access the agentic API through the MCP server (AWS Transform primitives)
- Agents can get the job
- Agents can generate a job plan and publish it to the job plan tree
- Agents can execute the plan by calling specific subagents or tools
- Agents can complete the job
- Agents can be stopped and resumed
- Agents should respond to the health check
- Agents produced trajectories shall be in the formation of open telemetry.
- Agents can be checkpointed

## Bedrock AgentCore Deployed Agent Testing

After completing developer local testing, one should consider package the agent code, deploy to Bedrock AgentCore and test invoking the deployed agent in Bedrock AgentCore once more.

This testing process simulates how AWS Transform service invokes the deployed agent in production, making sure any potential integration issues are uncovered.

### Build and Publish Agent Docker Image

```
DOCKER_REPO=orch-agent
ECR_REPO=my-orch-agent
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=XXXXXXXXXXXX
```

Wrap up all the local changes and rebuild the local docker container image with platform ARM since agent core only support ARM platform so far.

```bash
docker build --platform linux/arm64 -t ${DOCKER_REPO} -f Dockerfile .
```

(Optional) If you haven't created an ECR repository to bush the image, run the following to create an ECR repository,

```bash
aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION}
```

Tag the container and upload it to ECR in your AWS account

```bash
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
docker tag $(docker images ${DOCKER_REPO} --quiet | head -n 1) ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest
```

Publish the image to ECR

```bash
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest
```

### Create Bedrock AgentCore Execution Role

Bedrock AgentCore Runtime requires one execution role to assume so that the agent instance could access AWS Transform service and other AWS resources, use the following template to create an IAM role,

AgentCoreExecutionRole:

AWSTemplateFormatVersion: '2010-09-09' Description: IAM Execution Role for Bedrock Agent Core

Resources: AgentCoreExecutionRole: Type: 'AWS::IAM::Role' Properties: RoleName: AgentCoreExecutionRole AssumeRolePolicyDocument: Version: '2012-10-17' Statement: - Effect: Allow Principal: Service: - bedrock-agentcore.amazonaws.com Action: 'sts:AssumeRole' Policies: - PolicyName: BedrockAgentCoreExecutionPolicy PolicyDocument: Version: '2012-10-17' Statement: - Sid: ECRImageAccess Effect: Allow Action: - ecr:BatchGetImage - ecr:GetDownloadUrlForLayer Resource: - "arn:aws:ecr:us-east-1:XXXXXXXXXXXX:repository/*"

- Effect: Allow Action: - logs:DescribeLogStreams - logs:CreateLogGroup Resource: - "arn:aws:logs:us-east-1:XXXXXXXXXXXX:log-group:/aws/bedrock-agentcore/runtimes/*"

- Effect: Allow Action: - logs:DescribeLogGroups Resource: - "arn:aws:logs:us-east-1:XXXXXXXXXXXX:log-group:*"

- Effect: Allow Action: - logs:CreateLogStream - logs:PutLogEvents Resource: - "arn:aws:logs:us-east-1:XXXXXXXXXXXX:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"

- Sid: ECRTokenAccess Effect: Allow Action: - ecr:GetAuthorizationToken Resource: "*"

- Effect: Allow Action: - xray:PutTraceSegments - xray:PutTelemetryRecords - xray:GetSamplingRules - xray:GetSamplingTargets Resource: - "*"

- Effect: Allow Resource: "*" Action: cloudwatch:PutMetricData Condition: StringEquals: cloudwatch:namespace: bedrock-agentcore

- Sid: GetAgentAccessToken Effect: Allow Action: - bedrock-agentcore:GetWorkloadAccessToken - bedrock-agentcore:GetWorkloadAccessTokenForJWT - bedrock-agentcore:GetWorkloadAccessTokenForUserId Resource: - arn:aws:bedrock-agentcore:us-east-1:XXXXXXXXXXXX:workload-identity-directory/default - arn:aws:bedrock-agentcore:us-east-1:XXXXXXXXXXXX:workload-identity-directory/default/workload-identity/agentName-*

- Sid: BedrockModelInvocation Effect: Allow Action: - bedrock:InvokeModel - bedrock:InvokeModelWithResponseStream Resource: - "arn:aws:bedrock:*::foundation-model/*" - "arn:aws:bedrock:us-east-1:XXXXXXXXXXXX:*"

- Sid: TransformAgentsApiPolicy Effect: Allow Action: - "transform-agents:*" Resource: - "*"

NOTE: When adding permissions for transform-agents using the IAM console, it may show an Error indicating Invalid Service in Action. This is because the service is not yet a public AWS Service. This is not a blocker, and clicking Next should create the IAM policy.

![IAM console "Invalid Service In Action" policy validation warning for transform-agents](media/image8.svg)

### Create Bedrock AgentCore Runtime

Run the following command to recreate a Bedrock AgentCore Runtime:

For the RoleArn parameter, please provide the IAM role ARN created in step 5.2.2

```bash
AGENT_CORE_RUNTIME_NAME=myorchagent
AGENT_CORE_RUNTIME_DESCRIPTION="Orchestrator agent"
AGENT_CORE_RUNTIME_ROLE_NAME=AgentCoreExecutionRole
ATX_STAGE=prod
aws bedrock-agentcore-control create-agent-runtime \
--agent-runtime-name "$AGENT_CORE_RUNTIME_NAME" \
--description "${AGENT_CORE_RUNTIME_DESCRIPTION}" \
--agent-runtime-artifact '{"containerConfiguration":{"containerUri":"'${AWS_ACCOUNT_ID}'.dkr.ecr.'${AWS_REGION}'.amazonaws.com/'${ECR_REPO}':latest"}}' \
--role-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${AGENT_CORE_RUNTIME_ROLE_NAME}" \
--network-configuration '{"networkMode":"PUBLIC"}' \
--protocol-configuration '{"serverProtocol":"HTTP"}' \
--environment-variables '{"STAGE":"'${ATX_STAGE}'"}' \
--region ${AWS_REGION}
```

You should see an output like the following,

```json
{
 "agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:<account_id>:runtime/myorchagent-cPfBc86tYG",
 "workloadIdentityDetails": {
  "workloadIdentityArn": "arn:aws:bedrock-agentcore:us-east-1:<account_id>:workload-id entity-directory/default/workload-identity/myorchagent-cPfBc86tYG"
  },
 "agentRuntimeId": "myorchagent-cPfBc86tYG",
 "agentRuntimeVersion": "1",
 "createdAt": "2025-09-14T22:59:16.219208+00:00",
 "status": "CREATING"
}
```

### Invoke Bedrock AgentCore Runtime

#### Bedrock AgentCore Sandbox

TBD

#### AWS CLI

After the Bedrock AgentCore Runtime is successfully deployed, you may simulate the process AWS Transform invoking your agent via running the following commands.

In order enable your agent communicating with AWS Transform service, same tokens used in 5.1.2 are needed to construct a payload. Note that the payload used to invoke Bedrock AgentCore Runtime needs to be encoded with Base64:

```bash
echo '{"jsonrpc":"2.0", "id":1, "method":"atx_agent/invoke","params":{"invocationContext":{"jobMetadata":{"workspaceId":"'$WORKSPACE_ID'","jobId":"'$JOB_ID'"},"authorizationToken":"'$AUTHORIZATION_TOKEN'"},"agentInstanceId":"'$AGENT_INSTANCE_ID'"}}' | base64
aws bedrock-agentcore invoke-agent-runtime \
--agent-runtime-arn "arn:aws:bedrock-agentcore:us-east-1:<account_id>:runtime/myorchagent-cPfBc86tYG" \
--content-type "application/json" \
--accept "application/json" \
--payload '<base64 payload>' \
--region us-east-1 \
response.json
```

A successfully invocation of the agent shows something similar to the following.

```json
{
"runtimeSessionId": "72d9e817-cc48-4303-8a7c-6000e94e83ed",
"traceId": "Root=1-68c753f3-59493a73272dda6f3f3a48c0;Self=1-68c753f3-244ee838045c18525874fc8a",
"baggage": "Self=1-68c753f3-244ee838045c18525874fc8a,session.id=72d9e817-cc48-4303-8a7c-6000e94e83ed",
"contentType": "application/json",
"statusCode": 200
}
```

The CloudWatch Logs for the invocation would be available in a Log Group created for the AgentRuntime, eg.

```
/aws/bedrock-agentcore/runtimes/myorchagent-cPfBc86tYG -DEFAULT
```

### Testing Bedrock AgentCore Runtime with Additional Operations

#### Bedrock AgentCore Protocol Understanding

JSON-RPC 2.0 Communication: Bedrock AgentCore uses JSON-RPC 2.0 for all agent communication. Your agent receives these methods via /invocations:

- atx_agent/invoke - Agent invocation
- atx_agent/healthcheck - Health status check
- atx_agent/notify - Platform notifications
- atx_agent/restore - State restoration
- atx_agent/stop - Graceful shutdown
- message/send - A2A messaging (follows A2A protocol)
- tasks/get - Task retrieval

Session Isolation: Bedrock AgentCore uses runtimeSessionId for isolation. AWS Transform automatically generates session IDs using:

```
workspaceId_jobId_agentInstanceId
```

#### Test message/send

message/send operation is an important operation used for,

- Orchestrator Agent <-> AWS Transform Chat
- Orchestrator Agent <-> Task Agent
- Task Agent <-> Task Agent

Communications.

You may test if your agent can receive a message/send call via the following commands. Firstly construct the payload using Base64,

```bash
export MESSAGE=<Some natural language utterances to test your agent>
echo '{"jsonrpc":"2.0","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"'$MESSAGE'"}],"messageId":"'$(uuidgen)'","kind":"message","metadata":{"ATX_A2A.AgentInitializationContext":{"jobMetadata":{"workspaceId":"'$WORKSPACE_ID'","jobId":"'$JOB_ID'"},"agentInstanceId":"'$AGENT_INSTANCE_ID'","authorizationToken":"'$AUTHORIZATION_TOKEN'"}},"extensions":["ATX_A2A.AgentInitializationContext"]}}}' | base64
```

Now you may invoke your agent with,

```bash
aws bedrock-agentcore invoke-agent-runtime \
--agent-runtime-arn "arn:aws:bedrock-agentcore:us-east-1:<account_id>:runtime/myorchagent-cPfBc86tYG" \
--runtime-session-id "72d9e817-cc48-4303-8a7c-6000e94e83ed" \
--content-type "application/json" \
--accept "application/json" \
--payload 'eyJqc29ucnBjIjoiMi4wIiwibWV0aG9kIjoibWVzc2FnZS9zZW5kIiwicGFyYW1zIjp7Im1lc3NhZ2UiOnsicm9sZSI6InVzZXIiLCJwYXJ0cyI6W3sia2luZCI6InRleHQiLCJ0ZXh0IjoiV2hhdCBpcyBteSBqb2Igc3RhdHVzIn1dLCJtZXNzYWdlSWQiOiJENEI1Q0FDNC1COUI4LTRFOTUtODJGNy01RDdENTc0OEIxM0IiLCJraW5kIjoibWVzc2FnZSIsIm1ldGFkYXRhIjp7IkFUWF9BMkEuQWdlbnRJbml0aWFsaXphdGlvbkNvbnRleHQiOnsiam9iTWV0YWRhdGEiOnsid29ya3NwYWNlSWQiOiI0NTczZDllOC1jMTRmLTRiODQtYjE2Mi0yZGM3MWM0MWVmMDQiLCJqb2JJZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCJ9LCJhZ2VudEluc3RhbmNlSWQiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiLCJhdXRob3JpemF0aW9uVG9rZW4iOiJURU1QT1JBUllfQVVUSF
9CWVBBU1MifX0sImV4dGVuc2lvbnMiOlsiQVRYX0EyQS5BZ2VudEluaXRpYWxpemF0aW9uQ29udGV4dCJdfX19Cg==' \
--region us-east-1 \
response.json
```

A successfully invocation of the agent shows something like the following

```json
{
"runtimeSessionId": "72d9e817-cc48-4303-8a7c-6000e94e83ed",
"traceId": "Root=1-68c756f6-4a82e1b67369ed127625f74b;Self=1-68c756f6-70f4f8170c0cebe340d76dbb",
"baggage": "Self=1-68c756f6-70f4f8170c0cebe340d76dbb,session.id=72d9e817-cc48-4303-8a7c-6000e94e83ed",
"contentType": "application/json",
"statusCode": 200
}
```

You may see the response.json somewhat like,

```json
{"jsonrpc":"2.0","result":{"role":"agent","parts":[{"text":"I'm working on your request and will get back to you shortly.","kind":"text"}],"messageId":"D4B5CAC4-B9B8-4E95-82F7-5D7D5748B13B","kind":"message","metadata":null,"extensions":null,"referenceTaskIds":null,"taskId":null,"contextId":null},"error":null,"id":null}
```

# Onboarding and Production Webapp Testing

When you finish your developer testing and everything is working as expected, you can onboard your agent to AWS Transform production environment and use WebApp for agent testing.

You will go through three stages,

- Upload your local agent container into ECR
- Deploy your ECR agent container with Bedrock AgentCore,
- Bring the Bedrock AgentCore runtime ARN with AWS Transform to be invoked.

## Update local agent container into ECR

Please reference the Section 5.7 for how to Build and Publish Agent Image to publish image to your AWS account. After you push the image, you should be able to see an image with latest image tag with the recent pushed time.

![Update local agent container into ECR diagram](media/image9.png)

![Update local agent container into ECR diagram](media/image10.png)

## Deploy your ECR container with Bedrock AgentCore

### Create AgentCoreExecutionRole

Create AgentCoreExecutionRole in the IAM console with trusted Relationship using this template.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowAccessToBedrockAgentcore",
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock-agentcore.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

![Create AgentCoreExecutionRole diagram](media/image11.png)

Then add below inline policy named as `AWSTransformAgent-AgentCoreExecutionRolePolicy`. Replace the accountId to your own AWS account.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ECRImageAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer"
            ],
            "Resource": [
                "arn:aws:ecr:us-east-1:<AwsAccountId>:repository/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogStreams",
                "logs:CreateLogGroup"
            ],
            "Resource": [
                "arn:aws:logs:us-east-1:<AwsAccountId>:log-group:/aws/bedrock-agentcore/runtimes/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogGroups"
            ],
            "Resource": [
                "arn:aws:logs:us-east-1:<AwsAccountId>:log-group:*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": [
                "arn:aws:logs:us-east-1:<AwsAccountId>:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
            ]
        },
        {
            "Sid": "ECRTokenAccess",
            "Effect": "Allow",
            "Action": [
                "ecr:GetAuthorizationToken"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Effect": "Allow",
            "Resource": "*",
            "Action": "cloudwatch:PutMetricData",
            "Condition": {
                "StringEquals": {
                    "cloudwatch:namespace": "bedrock-agentcore"
                }
            }
        },
        {
            "Sid": "GetAgentAccessToken",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
            ],
            "Resource": [
                "arn:aws:bedrock-agentcore:us-east-1:<AwsAccountId>:workload-identity-directory/default",
                "arn:aws:bedrock-agentcore:us-east-1:<AwsAccountId>:workload-identity-directory/default/workload-identity/*"
            ]
        },
        {
            "Sid": "BedrockModelInvocation",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/*",
                "arn:aws:bedrock:us-east-1:<AwsAccountId>:*"
            ]
        },
        {
            "Sid": "TransformAgentsApiPolicy",
            "Effect": "Allow",
            "Action": [
                "transform-agents:*"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```

![Create AgentCoreExecutionRole diagram](media/image12.png)

You could see 2 Errors shown up in IAM policy but it's fine to proceed with next button.

![Create AgentCoreExecutionRole diagram](media/image13.png)

### Create Bedrock AgentCore Runtime

Create Bedrock AgentCore Runtime in Account-A by specifying the image URI and AgentCoreExecutionRole and following environment variables

- STAGE: prod
- REGION: us-east-1

![Create Bedrock AgentCore Runtime diagram](media/image14.png)

Click the hosting Agent and you could be able to provision the Agent Runtime and you can find the `agentRuntimeArn` in "View invocation code".

![Create Bedrock AgentCore Runtime diagram](media/image15.png)

## Register Agent with AWS Transform

In this step you will register your agent with AWS Transform, you may publish new versions, update access control with sub-sequent APIs. We provide the production endpoint

- Production endpoint: https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev

Depending on your testing scenarios, you need to register agent with different configuration regarding two fields:

- `customerConfigurationRequired`: Required.
- keep it `false` during your development/testing phase to verify agent functionality.

Set to `true` when agent is ready for customer to use. Agent would be deployed to your customer's Bedrock AgentCore Runtime.

- ` customerConfiguredAgentDependencies`: Optional, required only for orchestrator agents that depend on customer-configured subagents when `customerConfigurationRequired` is set as `true`

Other New required fields:

- `ownerType`
- `DIRECT_AGENT`: you allow list your agents to be visible to selected customers AWS account IDs
- `MARKETPLACE_AGENT`: agents distributed via AWS Agent Market Place

Other New optional fields

- `jobOrchestrator`: default value is false, set it as true if this agent is Orchestrator Agent.
- `jobOrchestratorMetadata`: optional
- chatUILabel: required, displaying agent name in the selection buttons of AWS Transform chat
- chatAgentIdentifier: required, String used by agent for quick detection of capabilities in AWS Transform chat.
- a2aSupported: required, if agent supports A2A
- Example json - `register-agent.json`

```json
{
  "name": "dynamic-showcase-agent-agentcore",
  "metadata": {
    "type": "ORCHESTRATOR_AGENT",
    "description": "Deep",
    "ownerName": "linchenk",
    "ownerContactInfo": "linchenk+test@amazon.com",
    "ownerType": "DIRECT_AGENT",
    "customerConfigurationRequired": false,
    "jobOrchestrator": true,
    "jobOrchestratorMetadata": {
      "chatUILabel": "Deep research Agent to perform general transformation",
      "chatAgentIdentifier": "dynamic-showcase-agent-agentcore",
      "a2aSupported": true
    }
  }
}
```

Register the agent with your own AWS credential

```bash
aws agent-registry register-agent \
    --cli-input-json file://register-agent.json \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
--region us-east-1
```

Expected response:

```json
{
    "name": "dynamic-showcase-agent-agentcore",
"visibility": "RESTRICTED"
}
```

### Publish An Agent Version

Before publishing an agent version, make sure to create a role(named: AWSTransformAgentInvokeRole) for AWS Transform to assume to invoke your Agent Core runtime.

- Trust policy for this role

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Effect": "Allow",
			"Principal": {
				"Service": "prod.us-east-1.compute.elastic-gumby.aws.internal"
			},
			"Action": "sts:AssumeRole"
```

![Publish An Agent Version diagram](media/image16.png)

}

]

}

- Create an inline policy with below template and named as `AWSTransform-BedrockAgentRuntimePolicy` and then attach to this role

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "bedrock-agentcore:GetAgentRuntime",
                "bedrock-agentcore:GetAgentRuntimeEndpoint",
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:ListAgentRuntimeEndpoints",
                "bedrock-agentcore:ListAgentRuntimeVersions",
                "bedrock-agentcore:ListAgentRuntimes",
                "bedrock-agentcore:StopRuntimeSession"
            ],
            "Resource": "*",
            "Effect": "Allow",
            "Sid": "AWSTransformAgentCoreRuntimePermissions"
        }
    ]
}
```

![Publish An Agent Version diagram](media/image17.png)

Now create your agent version configuration. Example JSON `publish-agent-version.json`. Change the accountId in the `atxAccessRoleArn` and replace your own Bedrock AgentCore Runtime Arn.

```json
{
  "name": "dynamic-showcase-agent-agentcore",
  "version": "1.0.0",
  "configuration": {
    "shortDescription": "Deep research Agent to perform general transformation",
    "computeConfiguration": {
      "provisionedComputeConfiguration": {
        "agentCoreConfiguration": {
          "atxAccessRoleArn": "arn:aws:iam::<AwsAccountId>:role/AWSTransformAgentInvokeRole",
          "runtimeArn": "arn:aws:bedrock-agentcore:us-east-1:<AwsAccountId>:runtime/dynamic_showcase_agent-SpNsIl2ASS",
          "qualifier": "DEFAULT"
        }
      }
    },
    "agentResiliencyConfiguration": {
      "partnerControllerRetryWindowMinutes": 6,
      "agentRecoveryConfiguration": {
        "recoveryWaitTimeSeconds": 60
      }
    },
    "inputPayloadSchema": {
      "$schema": "http://json-schema.org/draft-07/schema#",
      "type": "object",
      "properties": {}
    },
    "outputPayloadSchema": {
      "$schema": "http://json-schema.org/draft-07/schema#",
      "type": "object",
      "properties": {}
    },
    "monitoringType": "HEALTHCHECK",
    "notificationsEnabled": "ENABLED",
    "objectiveNegotiationPrompt": "<features>\\nWe can help test the new tools and capabilities in the platform orchestrator agent within AgentCore compute environment\\n</features>\\n\\n<supports_objective_negotiation>\\nNo.\\nThis agent does not allow changing the default objective.\\n</supports_objective_negotiation>\\n\\n<examples>\\n <valid>\\n Objective: Test the platform orchestrator agent\\n </valid>\\n\\n <valid>\\n Objective:Test new tools supported by platform orchestrator agent\\n </valid>\\n\\n <invalid>\\n Objective: Help me fix my bike.\\n Reason: Completely out of domain,\\n </invalid>\\n</examples>",
    "agentCard": {}
  }
}
```

Publish the version:

```bash
aws agent-registry publish-agent-version \
    --cli-input-json file://publish-agent-version.json \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
    --region us-east-1
```

Expected response:

```json
{
    "name": "dynamic-showcase-agent-agentcore",
    "version": "1.0.1",
    "status": "ACTIVE"
}
```

### Configure Access Control

By default, agents are created with RESTRICTED visibility. update-publisher-access-control API allows to add authorized AWS accounts to use the agents.

Example JSON - `access-control.json`. You can use the Agent publisher accountId as the customerAccountId for development testing.

```json
{
    "agentName": "dynamic-showcase-agent-agentcore",
    "customerAccountId": "<customerAccountId>",
    "accessControl": "ENABLED"
}
```

Update publisher access control:

```bash
aws agent-registry update-publisher-access-control \
    --cli-input-json file://access-control.json \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
    --region us-east-1
```

Verify access control:

```bash
aws agent-registry list-agent-access-control \
    --name dynamic-showcase-agent-agentcore \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
    --region us-east-1
```

Expected responses:

```json
{
    "customerAccountIdList": [
        "<customerAccountId>"
    ],
    "visibility": "RESTRICTED"
}
```

### Agent Management and Monitoring

#### List Your Published Agents

View all agents you have published to the Dynamic Registry:

```bash
aws agent-registry list-agents-by-publisher \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
    --region us-east-1
```

Expected responses:

```json
{
    "items": [
        "dynamic-showcase-agent-agentcore"
    ]
}
```

#### Get Agent Details

Retrieve metadata for a specific agent. Example JSON  - `get-agent-details.json`

```json
{
    "name": " dynamic-showcase-agent-agentcore",
    "version": "1.0.0"
}
aws agent-registry get-agent-version \
    --cli-input-json file://get-agent-details.json \
    --endpoint-url https://iad.prod.agent-registry-external.elastic-gumby.ai.aws.dev \
--region us-east-1
```

Expected response

```json
{
    "version": "1.0.0",
    "metadata": {
        "type": "ORCHESTRATOR_AGENT",
        "description": "Deep",
        "ownerName": "linchenk",
        "ownerAccountId": "<Account-A>",
        "ownerContactInfo": "linchenk+test@amazon.com",
        "ownerType": "DIRECT_AGENT",
        "customerConfigurationRequired": false,
        "customerConfiguredAgentDependencies": []
    },
    "visibility": "RESTRICTED",
    "configuration": {
        "shortDescription": "Deep research Agent to perform general transformation",
        "agentCard": {},
        "computeConfiguration": {
            "provisionedComputeConfiguration": {
                "agentCoreConfiguration": {
                    "atxAccessRoleArn": "arn:aws:iam::<AccountId>:role/AWSTransformAgentInvokeRole",
                    "runtimeArn": "arn:aws:bedrock-agentcore:us-east-1:<AccountId>:runtime/dynamic_showcase_agent-SpNsIl2ASS",
                    "qualifier": "DEFAULT"
                }
            }
        },
        "agentResiliencyConfiguration": {
            "partnerControllerRetryWindowMinutes": 6,
            "agentRecoveryConfiguration": {
                "recoveryWaitTimeSeconds": 60
            }
        },
        "inputPayloadSchema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {}
        },
        "outputPayloadSchema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {}
        },
        "monitoringType": "HEALTHCHECK",
        "notificationsEnabled": "ENABLED",
        "objectiveNegotiationPrompt": "<features>\\nWe can help test the new tools and capabilities in the platform orchestrator agent within AgentCore compute environment\\n</features>\\n\\n<supports_objective_negotiation>\\nNo.\\nThis agent does not allow changing the default objective.\\n</supports_objective_negotiation>\\n\\n<examples>\\n <valid>\\n Objective: Test the platform orchestrator agent\\n </valid>\\n\\n <valid>\\n Objective:Test new tools supported by platform orchestrator agent\\n </valid>\\n\\n <invalid>\\n Objective: Help me fix my bike.\\n Reason: Completely out of domain,\\n </invalid>\\n</examples>",
        "stopAgentConfiguration": {}
    },
    "status": "ACTIVE"
}
```

## AWS Transform Prod WebApp testing

You can create the AWS Transform profile in your own AWS account which is the `customerAccountId` allowlisted for agent usage and start testing without the assistance of SA. In this case, you can publish new version of agents and test it unlimited by yourself.

- Step1: Login your AWS console and go to `AWS Transform` service (https://us-east-1.console.aws.amazon.com/console/home?region=us-east-1#). Hit `Get started` and create the AWS Transform profile

![Figure  - Add new users from AWS Transform console](media/image18.png)

*Figure  - Add new users from AWS Transform console*

![Figure  - Add new users from AWS Transform console](media/image19.png)

*Figure  - Add new users from AWS Transform console*

In the setting, you could be able to see your AWS Transform application.

![Figure  - Add new users from AWS Transform console](media/image20.png)

*Figure  - Add new users from AWS Transform console*

- Step2: Add new users to AWS Transform, example like this. Or you can go to `IAM Identity Center` to create a group and add users there.

![Figure  - Add new users from AWS Transform console](media/image21.png)

*Figure  - Add new users from AWS Transform console*

![Figure  - Create a group and add users in IAM Identity Center](media/image22.png)

*Figure  - Create a group and add users in IAM Identity Center*

For each user that is allowed to access AWS Transform application, Admin needs to send email verification link and asks user to set up password.

![Figure  - Create a group and add users in IAM Identity Center](media/image23.png)

*Figure  - Create a group and add users in IAM Identity Center*

- Step3: Login the AWS Transform WebApp. Use the `Web application URL` in step 1 in AWS Transform console and paste it in the browser. It will lead you to the log in page and you can fill in username and password.

![Figure  - Create a group and add users in IAM Identity Center](media/image24.png)

*Figure  - Create a group and add users in IAM Identity Center*

- Step4: Create a new workspace and ask for questions like "What kind of job types are available to use?". Your registered agent should show up. For example, our registered agent is "dynamic-showcase-agent-agentcore". Then you can use natural language "create a job for 5. Dynamic-showcase-agent-agentcore"

![AWS Transform Prod WebApp testing diagram](media/image25.png)

Step5. For debugging, you would be able to get jobId directly from webapp url part - ` workspace/99a33b83-f739-4e83-8ff6-9eae537962cd/job/669f2d52-4f3e-4eb5-8bbd-b663c4fbad2d`. You can go to CloudWatch Logs Insights in your AWS account where you deploy the Bedrock AgentCore Runtime, to query by jobId and check agent log.

![AWS Transform Prod WebApp testing diagram](media/image26.png)

Example CloudWatch log query

```
fields @timestamp, @message, @logStream, @log
| filter @message like /<jobId>/
| sort @timestamp desc
| limit 10000
```

![AWS Transform Prod WebApp testing diagram](media/image27.png)

## External Agentic API support [To Be released]

AWS Transform will release external Agentic API support in Agent SDK which requires no allowlisting on AWS Transform side and could speed up the development. In order to use this feature, simply update the Bedrock AgentCore Runtime hosting to add the new environment variable `USE_EXTERNAL_AGENTIC_API=true`

Example screenshot:

![External Agentic API support (To Be released) diagram](media/image28.png)

For current testing, you can set `USE_EXTERNAL_AGENTIC_API=false` if your testing account is allowlisted to use Internal Agentic API

## Publish Agent to be consumed in customer account [WIP]

If you have finished the development testing, you can now make agent available to run in customer account. Instructions would be added later.

# FAQ

## AWS Transform Concepts FAQs

### What is job plan of an AWS Transform job?

AWS Transform job plan outlines the steps needed to complete a transformation job. The figure below shows an example job plan created by the agent to outline to the user how it is planning to complete the transformation job.

![Figure. Example of AWS Transform Job Plan Created by A Transformation Agent](media/image29.png)

*Figure. Example of AWS Transform Job Plan Created by A Transformation Agent*

To keep the customers informed with the job progress, the job plan is constantly being updated by the agent to reflect which steps are complete, which steps require human attention (also known as HITL tasks) and which steps are yet to complete.

### How is a job plan typically created?

A job plan is created by the agent performing the transformation job via invoking AWS Transform Job API (see section 8.2 AWS Transform Agentic API Specification for details).

Agent may invoke AWS Transform Job API with the following forms,

- A direct API invocation

Via AWS Transform Agentic MCP server

## AWS Transform Agent FAQs

This section covers commonly asked questions about AWS Transform agents, more details about using AWS Transform Base Agent package to develop AWS Transform agents can be found in 10.1.

### What is the minimum requirement for an agent to be an AWS Transform agent?

An AWS Transform agent is an agent that is cable of communicating with agents/customers via AWS Transform API and can perform transformation domain specific tasks.

This requires the agent runtime having:

- A HTTP server support /invocations and /ping API endpoints;
- The agent can get input job Id through environment variable or /invocations, get the job details, generate a plan, execute the plan and finish the job.

### Do I have to use AWS Transform provided base agent to build my agent?

No.

AWS Transform base agent provides a good starting point to build your domain agent. However, it is not necessary to use it. You can always build everything from scratch when you agent container follows the minimum agent requirement.

### May I use langgraph to build my agent instead of strands agent?

Yes.

You can either use langgraph or strands agent to build your domain agent.

### How the orchestrator agent select subagents?

When you create the orchestrator agent, you can specify which subagents can be used optionally. Or this process can be totally dynamically decided by orchestrator agent in the runtime, based on the subagents in the agent registry.

### How does Bedrock AgentCore integration work with AWS Transform?

Bedrock AgentCore provides a serverless runtime for AWS Transform agents using JSON-RPC 2.0 protocol.

Key aspects:

- Single Endpoint: All AWS Transform operations go through /invocations
- Session Isolation: Each job runs in isolated microVMs
- Automatic Context: AWS Transform context is extracted from any request type
- Protocol Compatibility: Supports both AWS Transform operations and A2A messaging
- Managed Infrastructure: No need to manage servers or scaling

### What's the difference between BaseAgent AgentRuntimeServer and the traditional CLI approach?

AgentRuntimeServer: Designed for Bedrock AgentCore, uses JSON-RPC, single endpoint

- Traditional CLI: Multiple REST endpoints, designed for MDE/ECS deployment
- Base Agent Package: Supports both approaches through different entry points

Both use the same BaseOrchestrator and agent factory pattern, so you can switch between deployment models with minimal code changes.

## HITL (Human-in-the-Loop) Task FAQs

### What are HITL (Human-in-the-Loop) Tasks?

HITL (Human-in-the-Loop) enables transformation agents to request human expertise at critical points during transformation processes. Tasks that appear in the Job Plan are marked as requiring human input. When agents need human input, they choose to pause execution and present relevant context to human operators, including files, configurations, and decision points. Human operators review the information, make necessary decisions or modifications, and approve continuation. This approach ensures complex transformations maintain accuracy while leveraging both AI agent efficiency and human judgment where expertise is most valuable.

### HITL (Human-in-the-Loop) blocking vs non-blocking

An agent produces a blocking HITL mean it will halt until human completes the task, while a non-blocking HITL task allows agents to continue transformation processes. Currently, we only support blocking HITL tasks for external agents.

### Standard vs critical HITL (Human-in-the-Loop) task

HITL tasks are classified as standard or critical. Standard HITL tasks can be approved and submitted by contributors, approvers, or administrators. Critical HITL tasks require approver or administrator roles for submission and are used for cases like code merges into main branches or production deployments.

### What are the available HITL (Human-in-the-Loop) UI for Agent?

# Troubleshooting

## Troubleshoot Local Testing - SSL: CERTIFICATE_VERIFY_FAILED Error with Boto3

### Symptom

When attempting to connect to an AWS endpoint using Boto3, you encounter an SSL error similar to the following:

```
botocore.exceptions.SSLError: SSL: CERTIFICATE_VERIFY_FAILED... unable to get local issuer certificate
```

This typically occurs when executing a command like

```
boto3.client(...)
```

### Root Cause

This issue most commonly arises in corporate environments that employ an SSL-intercepting proxy or firewall. The standard Boto3 certificate validation is affected in the following way:

- Proxy Interference: The corporate network appliance (proxy) intercepts and inspects all encrypted (HTTPS) traffic.
- Certificate Substitution: The proxy terminates the SSL connection and then re-establishes a new one to your machine. It uses a substitute certificate signed by an internal Corporate Certificate Authority (CA), not a publicly trusted one.
- Validation Failure: The Botocore library (used by Boto3) validates the certificate against its own built-in bundle of trusted CAs (botocore/cacert.pem). Since this bundle does not contain your corporate CA's root certificate, it cannot establish a valid chain of trust, resulting in the CERTIFICATE_VERIFY_FAILED error.

Certificate Chain Details

When the SSL handshake fails, the proxy presents its certificate, which is signed by your corporate CA. For example, a successful connection would look for a chain like this:

Target (Service): iad.prod.agenticapi.elastic-gumby.ai.aws.dev

- Intermediate CA: Amazon RSA 2048 M03
- Root CA: A trusted public root (contained in the Botocore bundle)

![Browser Certificate Viewer showing the Amazon-issued TLS certificate for the AWS Transform agentic API endpoint](media/image30.svg)

In a proxy environment, the handshake might present a different chain, which Botocore cannot validate:

- Proxy Target: A substitute certificate (signed by your Corporate CA)
- Proxy Intermediate CA: Your Corporate CA
- Proxy Root CA: Your Corporate Root CA

### Solution 1: Use a Combined CA Bundle

The recommended solution is to create a custom CA bundle that includes both the standard Botocore certificates and your corporate CA certificate. You then instruct Boto3 to use this combined bundle by setting the AWS_CA_BUNDLE environment variable.

- Obtain your Corporate CA Certificate: Request the certificate file (e.g., corporate-ca.pem) from your IT support team.
- Find the Botocore bundle: Locate the cacert.pem file within your virtual environment.

```python
BOTOCORE_BUNDLE=$(python3 -c "import botocore, os; print(os.path.join(os.path.dirname(botocore.__file__), 'cacert.pem'))")
echo $BOTOCORE_BUNDLE
```

- Create a combined bundle: Concatenate the two certificate files into a new, single file.

```bash
cat /path/to/corporate-ca.pem "$BOTOCORE_BUNDLE" > /path/to/my-combined-ca-bundle.pem
```

- Set the environment variable: Set the AWS_CA_BUNDLE environment variable to the path of your new combined bundle.

```bash
export AWS_CA_BUNDLE=/path/to/my-combined-ca-bundle.pem
```

- Verify: Run your Boto3 application.

### Solution 2: Use proxy_ca_bundle in Config

This method involves passing the path to the custom CA bundle directly in the Boto3 client's configuration. It is more granular than the environment variable method, as it only affects clients explicitly configured this way.

- Obtain your Corporate CA Certificate: Request the certificate file (e.g., corporate-ca.pem) from your IT support team.
- Combine the bundles: Follow steps 2 and 3 from Solution 1 to create a combined certificate bundle.

Update proxies and proxies_config in agent_builder_sdk/agentic_framework/client_factory.py to use corporate proxy

- Re-install AWS Transform dependencies via pip3 install -r requirements.txt with modified code

```python
"""
Client factory for AWS Transform Agentic API.
"""
import functools
import logging
import os
from typing import Optional
import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotocoreConfig
...
def create_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 30,
) -> BaseClient:
    # Get values from environment if not provided
    stage = stage or os.environ.get("STAGE")
    endpoint_url = endpoint_url or os.environ.get("QT_AGENTIC_API_ENDPOINT")
    region = region or os.environ.get("AWS_REGION", "us-east-1")
    if not endpoint_url and not (stage and region):
        raise ValueError("Either endpoint_url or both stage and region must be provided")
    combined_ca_bundle_path = '/path/to/my-combined-ca-bundle.pem'
    boto_config = BotocoreConfig(
        retries={"max_attempts": max_retries, "mode": "standard"},
        connect_timeout=timeout,
        read_timeout=timeout,
        proxies={
            'http': 'http://your_proxy_address:port',
            'https': 'https://your_proxy_address:port'
        },
        proxies_config={
            'Proxy_ca_bundle': combined_ca_bundle_path
        }
    )
    ...
```

### Solution 3: Temporarily Disable SSL Verification (Local Testing Only)

For local testing or in a controlled development environment, you can instruct Boto3 to skip SSL certificate validation entirely by setting verify=False when creating the client.

Update verify option in agent_builder_sdk/agentic_framework/client_factory.py to use corporate proxy

- Re-install AWS Transform dependencies via pip3 install -r requirements.txt with modified code

Security Warning: Disabling SSL verification is not recommended for production environments as it exposes your application to security risks, including man-in-the-middle attacks.

```python
"""
Client factory for AWS Transform Agentic API.
"""
import functools
import logging
import os
from typing import Optional
...
def create_agentic_api_client(
    stage: Optional[str] = None,
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 30,
) -> BaseClient:
    """
    Create boto3 client for AWS Transform Agentic API.
    Args:
        stage: Environment stage (defaults to env var)
        region: AWS region (defaults to env var)
        endpoint_url: Direct endpoint URL (overrides stage/region)
        max_retries: Maximum retries for API calls
        timeout: Timeout in seconds
    Returns:
        Configured boto3 client
    """
    # Get values from environment if not provided
    stage = stage or os.environ.get("STAGE")
    endpoint_url = endpoint_url or os.environ.get("QT_AGENTIC_API_ENDPOINT")
    region = region or os.environ.get("AWS_REGION", "us-east-1")
...
    if endpoint_url:
        return boto3.client(
            service_name=ATX_AGENTIC_API_SERVICE_NAME,
            endpoint_url=endpoint_url,
            region_name=region,
            config=boto_config,
            verify=False
        )
    else:
        return boto3.client(
            service_name=ATX_AGENTIC_API_SERVICE_NAME,
            endpoint_url=constructed_endpoint_url,
            region_name=region,
            config=boto_config,
            verify=False
        )
```

## Troubleshooting Bedrock AgentCore Testing - 422 Unprocessable Entity Error

A 422 Unprocessable Entity error in Bedrock AgentCore testing indicates that the server has validated the request's format but found semantic errors in the payload, preventing it from being processed. While a missing input field is a common cause, other validation issues can also trigger this error.

This troubleshooting guide provides steps to diagnose and resolve different causes of a 422 error.

### Symptom

The 422 Unprocessable Entity is usually triggered and can be seen from an invocation of a Bedrock AgentCore runtime instance, for example,

```bash
aws bedrock-agentcore invoke-agent-runtime \
--agent-runtime-arn "arn:aws:bedrock-agentcore:us-west-2:<account_id>:runtime/hosted_agent_vhusc-wjnEz2AJN3" \
--content-type "application/json" \
--accept "application/json" \
--payload $BASE64_MSG \
--region us-west-2 \
response.json
An error occurred (RuntimeClientError) when calling the InvokeAgentRuntime operation: Received error (422) from runtime. Please check your CloudWatch logs for more information.
```

### Step 1: Examine the Bedrock AgentCore logs in CloudWatch

The most detailed information about the validation failure will be in your agent's logs, published to Amazon CloudWatch. Search for the specific invocation that failed.

Run a query in CloudWatch Logs Insights to filter for the error message.

```
fields @timestamp, @message, @logStream, @log
| filter @message like /422/
| filter @message like /Unprocessable/
| sort @timestamp desc
| limit 10000
```

### Step 2: Validate general payload structure

Confirm that your request payload matches the expected JSON structure for the Bedrock AgentCore runtime.

Missing or incorrect fields: The Bedrock AgentCore runtime has specific requirements for the payload, including mandatory fields.

- Malformed JSON: Even if your test sends JSON, a syntax error (e.g., a misplaced comma or bracket) could cause the agent to fail during deserialization. Use a JSON linter to check for errors.
- Missing or incorrect Content-Type header: The server must be told that you are sending a JSON payload. Always include the Content-Type: application/json header in your request.

### Step 3: Validate AWS Transform specific payload structure

Agents built on Bedrock AgentCore for AWS Transform, is invoked by AWS Transform service with certain specific structure, for example, AWS Transform invokes Bedrock AgentCore agent following JSONRPC schema with different payload structure of different AWS Transform operations, make sure when your testing your Bedrock AgentCore runtime, with the exact same payload structure required by AWS Transform in Testing Bedrock AgentCore Runtime with Additional Operations.

## Troubleshooting "Either endpoint_url or both stage and region must be provided" in Bedrock AgentCore

The error message, "Either endpoint_url or both stage and region must be provided," indicates that the Bedrock AgentCore runtime is missing crucial configuration details. Specifically, it has not received the required environment variables to determine the correct API endpoint for your agent. This often occurs when the agent's deployment process fails to pass the necessary STAGE and REGION environment variables.

### Solution: Update the runtime environment variables

To fix this issue, you need to manually update the environment variables for your agent's runtime in the AWS console.

- Navigate to the Bedrock AgentCore console. Log in to the AWS Management Console and find the Bedrock AgentCore service.
- Locate your agent's runtime. In the Bedrock AgentCore dashboard, find and select the specific agent that is throwing the error.
- Update the hosting configuration. Within your agent's details page, you should find an "Update hosting" option. Click this button to modify the runtime settings.
- Access advanced configurations. A pop-up or new page will appear for configuring the agent's hosting. Look for an "Advanced configurations" section to manage environment variables.
- Add the STAGE environment variable.
- Click on "Environment variables."
- Add a new key-value pair.
- For the Key, enter STAGE.
- For the Value, enter the name of your deployment stage (e.g., prod).

![Solution: Update the runtime environment variables diagram](media/image31.png)

# Appendix

## Base Agent Code Walkthrough

AWS Transform Base Agent code package is a foundational agent package for partners to easily extend and build their agents, built on Amazon's Strands framework with capabilities for production deployment.

### What This Package Provides

This is your starting point for building agents that integrate with the AWS Transform. Instead of building from scratch, you extend the AsyncBaseOrchestrator class and customize it for your specific use case.

### Core Architecture

- AsyncBaseOrchestrator and AsyncBaseSubagent: Extensible agent class built on Strands SDK
- Production Runtime: AgentRuntimeServer for containerized deployment (legacy FastAPI server also available)
- Development Tools: Console mode with tracing for local testing and debugging. See DEVELOPMENT.md

Platform Integration: Provided AWS Transform connectivity and lifecycle management

- Checkpointing Functionality: Background agent memory/conversation persistence with configurable triggers for recovery and continuity

### Understanding Agents and Entry Points

#### What is an Agent?

An agent is the core logic that processes requests and makes decisions. All agents implement the BaseAgent or AsyncBaseAgent protocol, which defines a standardized interface (process_message or process_message_async) that enables any agent implementing this protocol to be pluggable into our AgentRuntimeServer infrastructure and other components.

This package provides two BaseAgent implementations:

- BaseOrchestrator: Manages complex workflows and coordinates multiple tasks
- BaseSubagent: Handles specific, focused tasks within a workflow

Each also has an equivalent AsyncBaseAgent implementation: AsyncBaseOrchestrator and AsyncBaseSubagent. You probably want to use these async versions, especially if used with AgentRuntimeServer. The synchronous implementations call the asynchronous functions under the hood. Each call to invoke the agent creates a new asyncio event loop in a separate thread taken from a thread pool. This is inefficient, particularly when your application already has a running asyncio event loop (which is the case when using AgentRuntimeServer).

#### What is an Entry Point?

An entry point is the executable that starts your agent as a service (the entry command running in the container). This package provides following reference implementations:

- simple_cli_agent_core.py - (NEW) Simplified AgentRuntimeServer:
- Simplified interface: Combines both into a single unified server
- Agent factory pattern: Pluggable agent
- Compatible protocols: Supports both Bedrock AgentCore and AWS Transform agentic compute endpoints
- _simple_stateless_cli_agent_core.py - (NEW) StatelessAgentRuntimeServer:
- Stateless server: Uses StatelessAgentRuntimeServer for subagent deployments
- No storage dependency: Simplified runtime without persistent state
- Concurrent processing: Handles multiple requests simultaneously
- Agent factory pattern: Pluggable agent
- Compatible protocols: Supports both Bedrock AgentCore and AWS Transform agentic compute endpoints
- cli.py - For orchestrator agents:
- FastAPI server: HTTP endpoints for receiving requests
- Queue service: Processes requests sequentially to maintain state
- Single-threaded: Prevents requests from stepping on each other
- subagent_cli.py - For subagents:
- Subagent server: Lightweight server for subagent requests
- Stateless: Can handle concurrent requests without queue
- Simpler: No queue service needed for specialized tasks

See Runtime Architecture for how these components work together.

### Runtime Architecture

This section gives you an overview the runtime architecture of your agent as a Docker container.

#### Orchestrator Runtime Architecture

When running in production (container mode), your orchestrator agent operates as a service with the flow of

- HTTP Request → FastAPI server receives A2A messages or platform notifications
- Queue Enqueue → Requests are prioritized and queued for processing
- Sequential Processing → Queue service processes one request at a time
- Agent Execution → Your orchestrator handles the request using Strands framework
- Checkpoint Trigger → After successful processing, checkpoint callback increments conversation turns or time-based triggers

Background Checkpointing → Background task periodically saves agent state to AWS Transform

- Response → Results are returned via HTTP response or stored for async retrieval

```
┌──────────────────────────────────────────────────────────────┐
│                    Container Environment                     │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐  │
│  │                AgentRuntimeServer                      │  │
│  │                                                        │  │
│  │  ┌─────────────────┐    ┌────────────────────────────┐ │  │
│  │  │   FastAPI       │    │     Queue Service          │ │  │
│  │  │   Server        │────│  ┌──────────────────────┐  │ │  │
│  │  │                 │    │  │   Request Queue      │  │ │  │
│  │  │ • /message/send │    │  │  ┌──────────────────┐│  │ │  │
│  │  │ • /invocations  │    │  │  │ Priority Handling││  │ │  │
│  │  │ • /ping         │    │  │  └──────────────────┘│  │ │  │
│  │  └─────────────────┘    │  └──────────────────────┘  │ │  │
│  │                         └──────────┬─────────────────┘ │  │
│  │                                    │                   │  │
│  │                                    ▼                   │  │
│  │  ┌───────────────────────────────────────────────────┐ │  │
│  │  │          Your Custom Orchestrator                 │ │  │
│  │  │                                                   │ │  │
│  │  │  • AsyncBaseOrchestrator + Your Extensions        │ │  │
│  │  │  • Custom Tools & Logic                           │ │  │
│  │  │  • Conversation Management                        │ │  │
│  │  │  • Memory & Storage                               │ │  │
│  │  └───────────────────────────────────────────────────┘ │  │
│  │                                    │                   │  │
│  │                                    ▼                   │  │
│  │  ┌───────────────────────────────────────────────────┐ │  │
│  │  │                 Checkpointer                      │ │  │
│  │  │                                                   │ │  │
│  │  │  • Automatic State Restoration                    │ │  │
│  │  │  • Conversation/Time-based Triggers               │ │  │
│  │  │  • Background Checkpoint Creation                 │ │  │
│  │  │  • AWS Transform Integration                       │ │  │
│  │  │                                                   │ │  │
│  │  │  Checkpoints:                                     │ │  │
│  │  │  • Request Queue State                            │ │  │
│  │  │  • Agent Memory                                   │ │  │
│  │  │  • Conversation History                           │ │  │
│  │  └───────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

#### Subagent Architecture

When running in production (container mode), your subagent operates as a stateless service with the flow of:

- HTTP Request → Stateless server receives requests directly
- Concurrent Processing → Multiple requests can be handled simultaneously
- Agent Execution → Your subagent handles the request using Strands framework
- Response → Results are returned immediately via HTTP response

```
┌──────────────────────────────────────────────────────────────┐
│                    Container Environment                     │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Stateless FastAPI Server                   │ │
│  │                                                         │ │
│  │ • /message/send  • /invocations  • /ping                │ │
│  │ • Concurrent Processing                                 │ │
│  │ • No Queue Service Needed                               │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                        │                     │
│                                        ▼                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Your Custom Subagent                       │ │
│  │                                                         │ │
│  │  • AsyncBaseSubagent + Your Extensions                  │ │
│  │  • Specialized Tools & Logic                            │ │
│  │  • Stateless Processing                                 │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Building Orchestrator Agents

To proceed with building Orchestrator Agents, you're expected to complete 3.2	Setting Up Your Development Environment, with the following available:

- AWS Credentials: Bedrock access for model inference,
- MCP Binary:
- Agentic Model:

```bash
aws configure add-model --service-model file://$(pwd)/service-2.json --service-name transformagenticservice
```

- Python version: Configure your version set with recommended Python 3.11. Python 3.10 still works but is not officially supported.

#### Create Your Orchestrator Class

```python
# In your agent package (e.g., MyCustomAgent)
from agent_builder_sdk.orchestrator_strands.base_orchestrator import AsyncBaseOrchestrator
class MyCustomOrchestrator(AsyncBaseOrchestrator):
    """Your custom orchestrator implementation."""
    def __init__(self, **kwargs):
        super().__init__(
            system_prompt="You are a specialized orchestrator for...",
            **kwargs
        )
        # Add your custom tools, hooks, conversation implementation
```

See Strands Documentation for more details about hooks, etc.

#### Create Custom Tools (Optional)

Define your domain-specific tools using Strands decorators:

```python
# custom_tools.py
from strands.tools import tool
@tool
def my_custom_tool(param: str) -> str:
    """Your custom tool description."""
    return f"Processed: {param}"
@tool
def another_tool(value: int) -> bool:
    """Another example tool."""
    return value > 0
```

See Strands Tools Documentation for more details.

```
#### Create Your Entry Point - Bedrock AgentCore (Recommended)
```

For a simpler approach, use the new AgentRuntimeServer with a custom agent factory. This server is compatible with both Bedrock AgentCore runtime protocols and AWS Transform agentic compute endpoints. See simple_cli_agent_core.py for a complete example:

Implementation:

```python
# my_agent_cli.py
from agent_builder_sdk.server.agent_runtime_server import AgentRuntimeServer
from agent_builder_sdk.agent_factory import create_default_orchestrator
def main():
    # Create custom agent factory. Use create_default_orchestrator for our default OR create a new factory method for MyCustomOrchestrator
    def agent_factory(mcp_client, storage_dir):
        return create_default_orchestrator(
            mcp_client=mcp_client,
            storage_dir=storage_dir,
            system_prompt="Your custom system prompt here"
        )
    # Start server with your factory
    server = AgentRuntimeServer(
        agent_factory=agent_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
        storage_dir="/tmp/my_agent",
        checkpoint_strategy="conversation", #optional field, enable the checkpoint
        checkpoint_interval=10, #optional field, enable the checkpoint
    )
    server.start()
if __name__ == "__main__":
    main()
```

Supported JSON-RPC Methods: The server automatically handles these Bedrock AgentCore operations:

#### Create Your Entry Point - Old CLI Approach

The easiest way is to copy the existing cli.py and replace the agent with yours:

```python
# my_orchestrator_cli.py
# Copy from cli.py and modify the create_orchestrator function:
from my_custom_agent.custom_tools.sub_agent_tool import (my_custom_tool, another_tool)
def create_orchestrator(args, mcp_client: Optional[MCPClient]) -> MyCustomOrchestrator:
    """Override to return your custom orchestrator."""
    # Configure memory components (optional, custom component provided by AWS Transform)
    # - FileSystemRepository: File-based memory storage
    memory_storage_path = os.path.join(args.storage_dir, "memories")
    repository = FileSystemRepository(storage_path=memory_storage_path)
    # - EpisodicMemory: Episodic memory (events, decisions) management
    episodic_memory = EpisodicMemory(repository=repository)
    # - MemoryManager: Memory coordination
    memory_manager = MemoryManager(memories=[episodic_memory])
    # - Custom memory tool provided by AWS Transform
    memory_tool = MemoryTool(memory_manager)
    # Configure conversation management (optional, custom component provided by AWS Transform)
    # - FileMultiSourceConversationRepository: Multi-source conversation storage
    conversation_repository = FileMultiSourceConversationRepository(storage_dir=args.storage_dir)
    # Configure hooks (optional, custom component provided by AWS Transform)
    # - ConversationHookProvider: Before/after conversation events
    # - MemoryHookProvider: Before/after memory operations
    hooks = [
        ConversationHookProvider(repository=conversation_repository),
        MemoryHookProvider(memory_manager=memory_manager),
    ]
    # Create your custom orchestrator with available options:
    orchestrator = MyCustomOrchestrator(
        system_prompt="Your custom system prompt...",
        hooks=hooks,  # Custom lifecycle hooks
        model_id=args.model_id,  # Bedrock model selection
        # guardrail_id=args.guardrail_id,     # Bedrock guardrails ID (optional, requires CDK set up)
        mcp_clients=[mcp_client],  # AWS Transform agentic MCP added by default, add you custom MCP clients
        region_name=args.region,  # AWS region
        custom_tools=[memory_tool.memory, my_custom_tool, another_tool],  # Pass any of your custom tools
    )
    return orchestrator
# Keep all other methods from cli.py as-is
```

#### Local Testing

Set up environment variables according to Configuration and add agent-builder-agentic-mcp to -binaryLocation.

The --localTesting mode allows you to directly talk to the agent and get responses. Without --localTesting, you will be starting the local server, so you can follow the below API Reference below to test endpoints with curl.

```bash
# Build your package
bb release
# Console mode: Talk directly to the agent and get responses
python src/my_custom_agent/my_orchestrator_cli.py \
 --localTesting \
 --workingDir . \
 --storage-dir . \
 --binaryLocation agent-builder-agentic-mcp
# Server mode: Start local server and queue service to test API endpoints with curl in another terminal
python src/my_custom_agent/my_orchestrator_cli.py \
  --workingDir . \
  --storage-dir . \
  --binaryLocation agent-builder-agentic-mcp \
  --queueStoragePath .
```

### Building Subagents

#### Create Your Subagent Class

```python
# In your agent package (e.g., MyCustomSubagent)
from agent_builder_sdk.base_subagent.base_subagent import AsyncBaseSubagent
class MyCustomSubagent(AsyncBaseSubagent):
    """Your custom subagent implementation."""
    def __init__(self, **kwargs):
        super().__init__(
            system_prompt="You are a specialized subagent for...",
            **kwargs
        )
        # Add your custom tools and specialized logic
```

#### Create Custom Tools (Optional)

Define your domain-specific tools using Strands decorators:

```python
# custom_subagent_tools.py
from strands.tools import tool
@tool
def specialized_processing_tool(data: str) -> str:
    """Process data for specific subagent task."""
    return f"Processed: {data}"
@tool
def validation_tool(input_value: str) -> bool:
    """Validate input for subagent processing."""
    return len(input_value) > 0
```

See Strands Tools Documentation for more details.

#### Create Your Entry Point

The StatelessAgentRuntimeServer is well-suited for subagents as it handles requests without persistent state. However, you can use either server type with any agent type based on your requirements. This example shows the stateless approach for subagents. See _simple_stateless_cli_agent_core.py for a complete example:

Note: You can also use AgentRuntimeServer for subagents if you need persistent state or queue-based processing. Both server types work with any agent type.

```python
# my_subagent_cli.py
from agent_builder_sdk.server.stateless_agent_runtime_server import StatelessAgentRuntimeServer
from agent_builder_sdk.agent_factory import create_default_subagent
def main():
    # Create custom agent factory. Use create_default_subagent for our default OR create a new factory method for MyCustomSubagent
    def agent_factory(mcp_client):
        return create_default_subagent(
            mcp_client=mcp_client,
            system_prompt="Your custom subagent system prompt here"
        )
    # Start stateless server with your factory
    server = StatelessAgentRuntimeServer(
        agent_factory=agent_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp"
    )
    server.start()
if __name__ == "__main__":
    main()
```

#### Local Testing

Set up environment variables according to Configuration and add agent-builder-agentic-mcp to --binaryLocation. Start the localk server and follow the API Reference below to test endpoints with curl.

```bash
# Start local stateless server to test API endpoints with curl in another terminal
python src/my_custom_subagent/my_subagent_cli.py \
  --binaryLocation agent-builder-agentic-mcp
```

### API Reference

#### HTTP Endpoints

These endpoints correspond to Bedrock AgentCore runtime endpoints and A2A protocol specifications:

#### Notifications Handler (/invocations)

The package includes a provided AWS Transform system notification handler in notification_handler.py that helps handle notifications received from the AWS Transform.

The notification handler is used by default with the built-in FastAPI implementation for processing /invocations endpoint requests.

#### Checkpointing Functionality

The package includes built-in checkpointing functionality designed for stateful agents that maintain conversation history, memory, and request queue state. This feature is integrated directly into AgentRuntimeServer (not StatelessAgentRuntimeServer) and provides two checkpoint strategies: time-based and conversation-based triggers. Checkpointing enables automatic failover and state restoration, ensuring your stateful agent can recover from failures and continue conversations seamlessly without losing context or progress.

##### When to Use Each Strategy

Conversation-based checkpointing is ideal for:

- Interactive agents with user conversations
- Agents where each conversation turn represents meaningful progress
- Recommended for most orchestrator agents

Time-based checkpointing is ideal for:

- Long-running background processes
- Batch processing or automated workflows
- When you need predictable checkpoint intervals regardless of activity

##### Components

- CheckpointService: Manages checkpoint lifecycle and integrates with AgentRuntimeServer
- CheckpointRepository: Handles checkpoint data storage and retrieval
- CheckpointManager: Manages checkpoint business logic and workflow coordination
- CheckpointTriggers: Configurable triggers for when to create checkpoints

##### Usage

Enable checkpointing when creating your AgentRuntimeServer:

```
# Time-based checkpointing (every 30 minutes)
server = AgentRuntimeServer(
        agent_factory=my_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
        storage_dir="/tmp/my_agent",
        checkpoint_strategy="time",
        checkpoint_interval=30
)
# Conversation-based checkpointing (every 5 conversation turns)
server = AgentRuntimeServer(
        agent_factory=my_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
        storage_dir="/tmp/my_agent",
        checkpoint_strategy="conversation",
        checkpoint_interval=5
)
# Restoration-only mode (restores existing checkpoints but creates no new ones)
# Checkpointing is disabled
server = AgentRuntimeServer(
        agent_factory=my_factory,
        host="0.0.0.0",
        port=8080,
        binary_location="agent-builder-agentic-mcp",
        storage_dir="/tmp/my_agent"
)
```

### Configuration

#### Required Environment Variables

```bash
# AWS Transform Integration. Pass in real ones if you want to test calling Agentic APIs
export WORKSPACE_ID=your-workspace-id              # AWS Transform workspace identifier
export JOB_ID=your-job-id                          # Current job identifier
export AGENT_INSTANCE_ID=your-agent-instance-id    # Agent instance identifier
export AUTHORIZATION_TOKEN=<<MY_SECRET_TOKEN>>     # Auth token
# AWS Transform API Endpoint
export QT_AGENTIC_API_ENDPOINT=https://iad.prod.agenticapi.elastic-gumby.ai.aws.dev
# AWS Configuration
export AWS_REGION=us-west-2                        # AWS region for Bedrock
```

#### Optional Environment Variables

```bash
# Optional Bedrock configs
export BEDROCK_GUARDRAIL_ID=27brr38ufca0           # Bedrock guardrail ID
export BEDROCK_GUARDRAIL_VERSION=1                 # Guardrail version
```

#### Bedrock Guardrails

Bedrock guardrails provide content filtering and safety controls for your agent interactions. When configured, guardrails help ensure responses meet your organization's content policies.

- Setup: Guardrails must be created via CDK deployment - see AWS CDK Bedrock Guardrail documentation
- Configuration: Set BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION environment variables
- Optional: Guardrails are optional - agents will work without them but won't have content filtering

#### Available Tools & Integrations

Your agent automatically has access to AWS Transform tools via MCP integration (AWS Transform MCP).

## AWS Transform Agentic API Specification

### Common Error Responses

All operations may return the following standard errors:

- AccessDeniedException - Access denied to the requested resource
- InternalServerException - Internal server error occurred
- DependencyInternalServerException - Error in a dependency service
- ResourceNotFoundException - Requested resource not found
- ThrottlingException - Request rate limit exceeded
- ValidationException - Request validation failed
- ConflictException - Request conflicts with current resource state
- ServiceQuotaExceededException - Service quota limit exceeded
- TerminalResourceException - Resource is in a terminal state

### Data Types and Constraints

#### RequestContext

Common structure encapsulating Job Details and Caller Agent's identification expected in all requests.

Members:

```
- jobMetadata (JobMetadata) - REQUIRED - Represents the Transformation JobId and the Workspace Id
- agentInstanceId (String) - REQUIRED - UUID pattern - InvocationId of the agent making the API request
- authorizationToken (String) - REQUIRED - SENSITIVE - Token passed by the Agentic Platform to Partner Agents - Length: 1-4096 characters - Pattern: ^[.+=A-Za-z0-9_-]+$
```

#### JobMetadata

Represents the Transformation JobId and the Workspace Id.

Members:

```
- jobId (String) - REQUIRED - UUID pattern - Transformation job identifier
- workspaceId (String) - REQUIRED - UUID pattern - Workspace identifier
```

### Common Patterns

- UUID Pattern: ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$
- Agent ID Pattern: ^[a-z0-9-]+$
- Version Pattern: ^\d+\.\d+\.\d+(?:-dev-[a-zA-Z0-9]+)?$
- Step ID Pattern: ^[a-zA-Z0-9-_]+$

#### Pagination

- Default page size: 50 items
- Maximum page size: 100 items
- Use nextToken for pagination continuation

#### Idempotency

- Operations marked as idempotent support the idempotencyToken parameter
- Use UUID format for idempotency tokens
- Tokens ensure safe retry of operations

#### Sensitive Data

- Fields marked as SENSITIVE contain confidential information
- Handle with appropriate security measures
- Do not log or expose in error messages

### InvokeAgent

Purpose: API used by Partners to Invoke Agents Idempotent: Yes (when idempotencyToken is set)

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED - Common structure encapsulating Job Details and Caller Agent's identification
- agentId (String) - REQUIRED - Agent identifier (1-64 chars, pattern: ^[a-z0-9-]+$)
- inputPayload (AgentInputPayload) - Input payload for the agent
- idempotencyToken (String) - UUID pattern for idempotency
- agentVersion (String) - Version string (min 5 chars, pattern: ^\d+\.\d+\.\d+(?:-dev-[a-zA-Z0-9]+)?$)
```

Response: - agentInstanceId (String) - REQUIRED - UUID of the agent instance

### StopAgent

Purpose: Stop a running agent instance

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- agentInstanceId (String) - REQUIRED - UUID of agent instance to stop
```

Response: - Standard success response

### ListAgentInstances

Purpose: List agent instances with pagination support Idempotent: Yes

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- nextToken (String) - Pagination token
- maxResults (Integer) - Max results per page (1-100)
```

Response:

```
- agentInstances (List) - REQUIRED - List of agent instances
- nextToken (String) - Next pagination token
```

### GetAgentInstance

Purpose: Get details of a specific agent instance

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- agentInstanceId (String) - REQUIRED - UUID of agent instance
```

Response: - agentInstance (AgentInstance) - REQUIRED - Agent instance details

### UpdateAgentInstance

Purpose: Update agent instance configuration

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- agentInstanceId (String) - REQUIRED - UUID of agent instance
- updateRequest (UpdateAgentInstanceRequest) - REQUIRED - Update details
```

Response: - Standard success response

### ListArtifacts

Purpose: API used by Partner agents to list artifacts for a transformation job Idempotent: Yes Paginated: Yes

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- artifactFilter (ArtifactFilter) - Filter criteria for artifacts
- nextToken (String) - Pagination token
- maxResults (Integer) - Max results per page (1-100)
```

Response:

```
- artifacts (List) - REQUIRED - List of artifacts
- nextToken (String) - Next pagination token
```

### CreateArtifactUploadUrl

Purpose: Generate an S3 presigned URL for uploading an artifact

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- contentDigest (ContentDigest) - REQUIRED - Content hash/digest
- artifactReference (ArtifactReference) - REQUIRED - Artifact reference
- label (String) - Artifact label (1-100 chars)
- planStepId (String) - Plan step ID (1-64 chars, pattern: ^[a-zA-Z0-9-_]+$)
- visibility (Visibility) - REQUIRED - Default: "INTERNAL"
- metadata (MetadataContext) - Additional metadata
```

Response:

```
- artifactId (String) - REQUIRED - UUID of created artifact
- s3preSignedUrl (String) - REQUIRED - SENSITIVE - Presigned upload URL
- s3UrlExpiryTimestamp (Timestamp) - REQUIRED - URL expiration time
- requestHeaders (Map<String, List>) - REQUIRED - Required headers
```

### CreateArtifactDownloadUrl

Purpose: Generate an S3 presigned URL for downloading an artifact

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- artifactId (String) - REQUIRED - UUID of artifact to download
```

Response:

```
- s3preSignedUrl (String) - REQUIRED - SENSITIVE - Presigned download URL
- s3UrlExpiryTimestamp (Timestamp) - REQUIRED - URL expiration time
```

### CompleteArtifactUpload

Purpose: Complete the artifact upload process

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- artifactId (String) - REQUIRED - UUID of uploaded artifact
```

Response: - Standard success response

### GetArtifactMetadata

Purpose: Retrieve metadata for a specific artifact

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- artifactId (String) - REQUIRED - UUID of artifact
```

Response: - metadata (ArtifactMetadata) - REQUIRED - Artifact metadata

### CopyArtifact

Purpose: Copy an artifact to a new location

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- sourceArtifactId (String) - REQUIRED - UUID of source artifact
- destinationReference (ArtifactReference) - REQUIRED - Destination reference
```

Response: - artifactId (String) - REQUIRED - UUID of copied artifact

### GetJob

Purpose: Retrieve job details

Request Parameters: - requestContext (RequestContext) - REQUIRED

Response: - job (Job) - REQUIRED - Job details

### UpdateJobStatus

Purpose: Update the status of a job

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- status (JobStatus) - REQUIRED - New job status
- statusReason (String) - Reason for status change
```

Response: - Standard success response

### PutJobPlan

Purpose: Submit or update a job execution plan

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- plan (JobPlan) - REQUIRED - Job execution plan
```

Response: - Standard success response

### ListJobPlanSteps

Purpose: List steps in a job plan with pagination Paginated: Yes

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- nextToken (String) - Pagination token
- maxResults (Integer) - Max results per page (1-100)
```

Response:

```
- steps (List) - REQUIRED - List of plan steps
- nextToken (String) - Next pagination token
```

### UpdateJobPlanStep

Purpose: Update a specific job plan step

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- stepId (String) - REQUIRED - Step identifier
- updateRequest (UpdateJobPlanStepRequest) - REQUIRED - Update details
```

Response: - Standard success response

### DeleteJobPlanStep

Purpose: Delete a job plan step

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- stepId (String) - REQUIRED - Step identifier to delete
```

Response: - Standard success response

### CreateHitlTask

Purpose: Create a human-in-the-loop task

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- taskDefinition (HitlTaskDefinition) - REQUIRED - Task definition
- priority (TaskPriority) - Task priority level
```

Response: - taskId (String) - REQUIRED - UUID of created task

### ListHitlTasks

Purpose: List HITL tasks with pagination Paginated: Yes

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- filter (HitlTaskFilter) - Filter criteria - nextToken (String)
- Pagination token - maxResults (Integer) - Max results per page (1-100)
```

Response:

```
- tasks (List) - REQUIRED - List of HITL tasks
- nextToken (String) - Next pagination token
```

### GetHitlTask

Purpose: Get details of a specific HITL task

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- taskId (String) - REQUIRED - UUID of HITL task
```

Response: - task (HitlTask) - REQUIRED - HITL task details

### StartHitlTask

Purpose: Start execution of a HITL task

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- taskId (String) - REQUIRED - UUID of task to start
```

Response: - Standard success response

### CloseHitlTask

Purpose: Close a HITL task

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- taskId (String) - REQUIRED - UUID of task to close
- result (HitlTaskResult) - REQUIRED - Task completion result
```

Response: - Standard success response

### ListConnectors

Purpose: List available connectors with pagination Paginated: Yes

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- nextToken (String) - Pagination token
- maxResults (Integer) - Max results per page (1-100)
```

Response:

```
- connectors (List) - REQUIRED - List of connectors
- nextToken (String) - Next pagination token
```

### GetConnector

Purpose: Get details of a specific connector

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- connectorId (String) - REQUIRED - Connector identifier
```

Response: - connector (Connector) - REQUIRED - Connector details

### GetTemporaryCredentialsForConnector

Purpose: Get temporary AWS credentials for connector access

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- connectorId (String) - REQUIRED - Connector identifier
- durationSeconds (Integer) - Credential duration (900-43200 seconds)
```

Response:

```
- credentials (TemporaryCredentials) - REQUIRED - SENSITIVE - Temporary credentials
- expiration (Timestamp) - REQUIRED - Credential expiration time
```

### RefreshAuthToken

Purpose: Refresh authentication token

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- refreshToken (String) - REQUIRED - SENSITIVE - Refresh token
```

Response:

```
- accessToken (String) - REQUIRED - SENSITIVE - New access token
- expiresIn (Integer) - REQUIRED - Token lifetime in seconds
```

### SendMessage

Purpose: Send a message within the system

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- message (Message) - REQUIRED - Message content
- recipients (List) - REQUIRED - Message recipients
```

Response: - messageId (String) - REQUIRED - UUID of sent message

### CreateWorklog

Purpose: Create a work log entry

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- worklogEntry (WorklogEntry) - REQUIRED - Work log details
```

Response: - worklogId (String) - REQUIRED - UUID of created worklog

### TestOperation

Purpose: Test operation for development/debugging

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- testPayload (TestPayload) - Test data
```

Response: - result (TestResult) - REQUIRED - Test execution result

### PreProdTestOperation

Purpose: Pre-production test operation

Request Parameters:

```
- requestContext (RequestContext) - REQUIRED
- testConfig (PreProdTestConfig) - REQUIRED - Test configuration
```

Response: - testResults (PreProdTestResults) - REQUIRED - Test execution results

## AWS Transform Agent Registry External API Specification

This section provides comprehensive API documentation for the AWS Transform Dynamic Agent Registry, including new features for access control, provisioned compute support, and customer configuration management.

### Common Error Responses

All operations may return the following standard errors:

- AccessDeniedException - Access denied to the requested resource
- InternalServerException - Internal server error occurred
- ResourceNotFoundException - Requested resource not found
- ThrottlingException - Request rate limit exceeded
- ValidationException - Request validation failed
- ConflictException - Request conflicts with current resource state

### Data Types and Constraints

#### RegisterAgentMetadata

Structure containing agent metadata information.

Members:

```
- type (AgentType) - REQUIRED - Type of the agent
- description (String) - REQUIRED - Description of the agent
- ownerName (String) - REQUIRED - Name of the agent owner
- ownerAccountId (String) - REQUIRED - AWS Account ID pattern: ^[0-9]{12}$ - Owner account identifier
- ownerContactInfo (String) - REQUIRED - Contact information for notifications about agent
- customerConfigurationRequired (Boolean) - REQUIRED - NEW - Whether customer configuration is required
- customerConfiguredAgentDependencies (List<String>) - OPTIONAL - NEW - List of customer-configured agent dependencies
```

#### OwnerType

Enumeration for agent owner types.

Members:

```
- `DIRECT_AGENT` - Agents directly listed to allowlisted customers by agent publisher
- `MARKETPLACE_AGENT` - Marketplace registered agents
- `INTERNAL_AGENT` - Internal AWS Transform developed agents
```

#### AgentConfiguration

Structure containing agent configuration details.

Members:

```
- shortDescription (String) - REQUIRED - Brief description of the agent
- agentCard (Document) - REQUIRED - JSON containing A2A-style Card Data
- computeConfiguration (ComputeConfiguration) - REQUIRED - Compute configuration settings
- agentResiliencyConfiguration (AgentResiliencyConfiguration) - OPTIONAL - Resiliency settings
- inputPayloadSchema (Document) - REQUIRED - Schema for input payload
- outputPayloadSchema (Document) - REQUIRED - Schema for output payload
- monitoringType (MonitoringType) - REQUIRED - Type of monitoring enabled
- notificationsEnabled (NotificationStatus) - REQUIRED - Whether notifications are enabled
- objectiveNegotiationPrompt (String) - REQUIRED - Prompt for objective negotiation
```

#### ComputeConfiguration

Union type for compute configuration options.

Options:

```
- legacyComputeConfiguration (LegacyComputeConfiguration) - REQUIRED - Legacy compute configuration
- provisionedComputeConfiguration (ProvisionedComputeConfiguration) - REQUIRED - Provisioned compute configuration
```

#### MonitoringType

Enumeration for monitoring types.

Values:

```
- HEARTBEAT - Heartbeat-based monitoring
- HEALTHCHECK - Health check-based monitoring
```

#### NotificationStatus

Enumeration for notification status.

Values:

```
- ENABLED - Notifications are enabled
- DISABLED - Notifications are disabled
```

#### AgentVisibility

Enumeration for agent visibility settings.

Values:

```
- PUBLIC - Agent is publicly visible
- RESTRICTED - Agent has restricted visibility
```

#### VersionStatus

Enumeration for version status.

Values:

```
- CREATED - Status when entry is first received
- IN_VERIFICATION - Status when entry is under the validation workflow
- ACTIVE - Status when validation is complete and the version is actively available
- VERIFICATION_FAILED - Status when validation workflow fails for the version
```

#### AccessControl

Enumeration for access control settings.

Values:

```
- ENABLED - Access control is enabled
- DISABLED - Access control is disabled
```

#### ProvisionedComputeConfiguration

Union type for provisioned compute configuration options.

Options:

```
- mdeConfiguration (MDEConfiguration) - REQUIRED - MDE configuration settings
- agentCoreConfiguration (AgentCoreConfiguration) - REQUIRED - Agent core configuration settings
```

#### LegacyComputeConfiguration

Structure for legacy compute configuration.

Members:

```
- endpoint (String) - Service endpoint
- region (String) - AWS region
```

#### RegisterAgentMetadata

Structure containing agent registration metadata.

Members:

```
- type (AgentType) - REQUIRED - Type of the agent
- description (String) - REQUIRED - Description of the agent
- ownerName (String) - REQUIRED - Name of the agent owner
- ownerContactInfo (String) - REQUIRED - Contact information for notifications about agent
```

#### AgentType

Enumeration for agent types.

Values:

```
- ORCHESTRATOR_AGENT - Orchestrator agent type
- SUB_AGENT - Sub-agent type
```

#### MDEConfiguration

Structure for MDE configuration settings.

Members:

```
- atxAccessRoleArn (String) - REQUIRED - AWS Transform access role ARN (pattern: ^(arn:aws:iam::[0-9]{12}:role/).+)
- bootstrapRoleArn (String) - REQUIRED - Bootstrap role ARN for MDE service setup (pattern: ^(arn:aws:iam::[0-9]{12}:role/).+)
- environmentRoleArn (String) - REQUIRED - Runtime environment role ARN (pattern: ^(arn:aws:iam::[0-9]{12}:role/).+)
- storageSize (Integer) - REQUIRED - Storage size in GB (0-64)
- devfile (String) - REQUIRED - Devfile configuration
- instanceType (String) - REQUIRED - EC2 instance type
```

#### AgentCoreConfiguration

Structure for Agent Core configuration settings.

Members:

```
- atxAccessRoleArn (String) - REQUIRED - AWS Transform access role ARN (pattern: ^(arn:aws:iam::[0-9]{12}:role/).+)
```

- runtimeArn (String) - REQUIRED - ARN of the Bedrock AgentCore Runtime Resource

```
- qualifier (String) - Specific qualifier for runtime invocation (defaults to DEFAULT if not specified)
```

#### AgentResiliencyConfiguration

Structure for agent resiliency settings.

Members:

```
- partnerControllerRetryWindowMinutes (Integer) - OPTIONAL - Retry window in minutes
- agentRecoveryConfiguration (AgentRecoveryConfiguration) - OPTIONAL - Recovery configuration
```

#### AgentRecoveryConfiguration

Structure for agent recovery settings.

Members:

```
- recoveryWaitTimeSeconds (Integer) - REQUIRED - Wait time before recovery in seconds
```

### Common Patterns

- Agent Name Pattern: ^[a-zA-Z0-9_-]+$
- Version Pattern: ^\d+\.\d+\.\d+(?:-dev-[a-zA-Z0-9]+)?$
- Account ID Pattern: ^[0-9]{12}$
- UUID Pattern: ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$

#### Pagination

- Default page size: 50 items
- Maximum page size: 50 items
- Use nextToken for pagination continuation

#### Idempotency

- Operations marked as idempotent support the idempotencyToken parameter
- Use UUID format for idempotency tokens
- Tokens ensure safe retry of operations

### GetAgent

Purpose: Operation to access and view an agent's metadata and current configuration details

Request Parameters:

```
- name (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
```

Response:

```
- metadata (AgentMetadata) - Agent metadata information
- visibility (AgentVisibility) - Agent visibility settings
```

### GetAgentVersion

Purpose: Returns version-specific information, including the latest version details or information about a specific version when requested

Request Parameters:

```
- name (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
- version (String) - Version string (pattern: ^\d+\.\d+\.\d+(?:-dev-[a-zA-Z0-9]+)?$) - Returns latest active version if not provided
```

Response:

```
- version (String) - SemVer string
- metadata (AgentMetadata) - Agent metadata information
- visibility (AgentVisibility) - Agent visibility settings
- configuration (AgentConfiguration) - Agent configuration details
- status (VersionStatus) - REQUIRED - Version status
- statusMessage (String) - Status message
```

### RegisterAgent

Purpose: Operation to register a new agent with AWS Transform which creates the first version of agent

Idempotent: Yes (when idempotencyToken is set)

Request Parameters:

```
- name (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
- metadata (RegisterAgentMetadata) - REQUIRED - Agent registration metadata
- idempotencyToken (String) - UUID for idempotency
```

Response:

```
- name (String) - REQUIRED - Agent identifier
- visibility (AgentVisibility) - REQUIRED - Agent visibility settings
```

### PublishAgentVersion

Purpose: Operation publishing agent configurations necessary for agent invocation and management. Each version maintains distinct configuration settings

Idempotent: Yes (when idempotencyToken is set)

Request Parameters:

```
- name (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
- version (String) - REQUIRED - Version string (pattern: ^\d+\.\d+\.\d+(?:-dev-[a-zA-Z0-9]+)?$)
- configuration (AgentConfiguration) - REQUIRED - Agent configuration details
- idempotencyToken (String) - UUID for idempotency
```

Response:

```
- name (String) - REQUIRED - Agent identifier
- version (String) - REQUIRED - Version string
- status (VersionStatus) - REQUIRED - Version status
```

### ListAgentAccessControl

Purpose: Operation that lists agent managed access controls, for agents with RESTRICTED visibility, this API lists all AWS accounts that have been granted access permissions

Request Parameters:

```
- name (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
- maxResults (Integer) - Max results per page (1-50)
- nextToken (String) - Pagination token
```

Response:

```
- customerAccountIdList (List<String>) - List of customer account IDs
- visibility (AgentVisibility) - Agent visibility settings
- nextToken (String) - Next pagination token
```

### UpdatePublisherAccessControl

Purpose: Operation that allows an agent publishers to manage access control by adding or removing tenant AWS account IDs that can access their agents

Idempotent: Yes (when idempotencyToken is set)

Request Parameters:

```
- agentName (String) - REQUIRED - Agent identifier (pattern: ^[a-zA-Z0-9_-]+$)
- customerAccountId (String) - REQUIRED - Customer account ID (pattern: ^[0-9]{12}$)
- accessControl (AccessControl) - REQUIRED - Access control settings
- idempotencyToken (String) - UUID for idempotency
```

Response:

```
Standard success response
```

## HITL Component Input, Output, and Picture Example

Each component's input schema defines the required properties for UI components. The input schema specifies what properties the UI component accepts, while the output schema defines the JSON structure the component returns after users complete and submit their information.

### Text Input component

![Text Input component diagram](media/image32.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TextInput",
  "description": "A text input field component",
  "type": "object",
  "properties": {
    "label": {
      "description": "The label text for the input field",
      "type": "string"
    },
    "description": {
      "description": "The description text for the input field",
      "type": "string"
    },
    "value": {
      "description": "The initial value of the input field",
      "type": "string"
    },
    "placeholder": {
      "description": "The placeholder text for the input field",
      "type": "string"
    },
    "maxLength": {
      "description": "The maximum allowed length of the input value",
      "type": "integer"
    },
    "errorAlert": {
      "description": "Error alert configuration",
      "type": "object",
      "properties": {
        "header": {
          "description": "The header text for the error alert",
          "type": "string"
        },
        "description": {
          "description": "The description text for the error alert",
          "type": "string"
        }
      },
      "required": ["header"]
    }
  },
  "required": ["label", "value"]
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TextInputOutput",
  "description": "The output schema of Text Input",
  "type": "object",
  "properties": {
    "data": {
      "type": "string"
    }
  },
  "required": ["data"],
  "additionalProperties": false
}
```

### Auto Form component

![Auto Form component diagram](media/image33.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AutoForm",
  "description": "A dynamic form generator component that renders flexible forms using a JSON schema interface. Form fields are built using CloudScape components, with an extensible set of supported field types.",
  "supportedFieldTypes": [
    {
      "type": "text",
      "description": "Single-line text input",
      "validation": ["pattern", "minLength", "maxLength", "errorMessage"],
      "schema": "fields/text-field.schema.json"
    },
    {
      "type": "textarea",
      "description": "Multi-line text input",
      "validation": ["pattern", "minLength", "maxLength", "errorMessage"],
      "schema": "fields/textarea-field.schema.json"
    },
    {
      "type": "select",
      "description": "Single option selection dropdown",
      "validation": [],
      "required": ["options"],
      "schema": "fields/select-field.schema.json"
    },
    {
      "type": "radiogroup",
      "description": "Radio button group for single selection",
      "validation": [],
      "required": ["options"],
      "schema": "fields/radio-group-field.schema.json"
    },
    {
      "type": "multiselect",
      "description": "Multiple option selection dropdown",
      "validation": [],
      "required": ["options"],
      "schema": "fields/multiselect-field.schema.json"
    },
    {
      "type": "checkbox",
      "description": "Boolean checkbox for true/false selection",
      "validation": [],
      "required": [],
      "schema": "fields/checkbox-field.schema.json"
    },
    {
      "type": "jsonBlock",
      "description": "Multi-line JSON input with validation",
      "validation": ["errorMessage"],
      "schema": "fields/json-block-field.schema.json"
    },
    {
      "type": "fileUpload",
      "description": "File upload input with validation",
      "validation": ["maxFileSize", "allowedFileTypes", "maxFiles", "errorMessage"],
      "schema": "fields/file-upload-field.schema.json"
    }
  ],
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Optional form title displayed at the top"
    },
    "description": {
      "type": "string",
      "description": "Optional form description displayed below the title"
    },
    "fields": {
      "type": "array",
      "description": "Array of form fields to render. These will be arranged in the order they appear.",
      "minItems": 1,
      "items": {
        "oneOf": [
          { "$ref": "fields/text-field.schema.json" },
          { "$ref": "fields/textarea-field.schema.json" },
          { "$ref": "fields/select-field.schema.json" },
          { "$ref": "fields/radio-group-field.schema.json" },
          { "$ref": "fields/multiselect-field.schema.json" },
          { "$ref": "fields/checkbox-field.schema.json" },
          { "$ref": "fields/json-block-field.schema.json" },
          { "$ref": "fields/file-upload-field.schema.json" }
        ]
      }
    },
    "alerts": {
      "$ref": "components/alerts.schema.json"
    }
  },
  "required": ["fields"],
  "additionalProperties": false
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AutoFormOutput",
  "description": "The output schema of AutoForm component",
  "type": "object",
  "properties": {
    "data": {
      "type": "object",
      "description": "Form data as Record<string, FieldValue>",
      "patternProperties": {
        ".*": {
          "oneOf": [
            {
              "type": "string"
            },
            {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            {
              "type": "boolean"
            }
          ]
        }
      },
      "additionalProperties": false
    },
    "metadata": {
      "type": "object",
      "properties": {
        "schemaVersion": {
          "type": "string",
          "const": "1.0"
        },
        "fieldCount": {
          "type": "number",
          "minimum": 0
        },
        "validationStatus": {
          "type": "string",
          "enum": ["valid", "invalid"]
        },
        "timestamp": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": ["schemaVersion", "fieldCount", "validationStatus", "timestamp"],
      "additionalProperties": false
    }
  },
  "required": ["data", "metadata"],
  "additionalProperties": false
}
```

### File Upload component

![File Upload component diagram](media/image34.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "FileUploadComponent",
  "description": "A common component that allows user to upload multiple files with comprehensive error handling and validation. It saves the data as { uploadedFiles: FileData[] }, where FileData contains base64 encoded content, filename, and metadata.",
  "type": "object",
  "properties": {
    "label": {
      "description": "The label text for the file upload component",
      "type": "string"
    },
    "description": {
      "description": "The description text displayed below the label",
      "type": "string"
    },
    "constraintText": {
      "description": "The constraint text displayed below the upload area",
      "type": "string"
    },
    "uploadButtonText": {
      "description": "Custom text for the upload button",
      "type": "string",
      "default": "Choose file"
    },
    "maxFileSize": {
      "description": "Maximum file size allowed in bytes",
      "type": "number",
      "default": 10485760,
      "minimum": 1
    },
    "allowedFileTypes": {
      "description": "Array of allowed file extensions (without dots). Empty array allows all types.",
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9]+$"
      },
      "default": [],
      "examples": [
        ["pdf", "doc", "docx"],
        ["jpg", "jpeg", "png", "gif"],
        ["csv", "xlsx", "json"]
      ]
    },
    "errorMessage": {
      "description": "Server-side error message displayed at the top of the component",
      "type": "string"
    },
    "detailedErrorMessages": {
      "description": "Array of detailed server-side error messages for expandable error display",
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "onError": {
      "description": "Callback function called when an error occurs during file upload or validation",
      "type": "string",
      "format": "javascript-function"
    }
  },
  "required": ["label"],
  "additionalProperties": false
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GeneralConnectorHumanOutput",
  "description": "The output schema of File Upload Component",
  "type": "object",
  "properties": {
    "uploadedFile": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/FileData"
      }
    }
  },
  "required": ["uploadedFile"],
  "additionalProperties": false,
  "definitions": {
    "FileData": {
      "type": "object",
      "properties": {
        "content": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "isZip": {
          "type": "boolean"
        }
      },
      "required": ["content", "name", "isZip"],
      "additionalProperties": false
    }
  }
}
```

### Table component

![Table component diagram](media/image35.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TableComponent",
  "description": "A table component with column definitions, data items, filtering, pagination, and expandable rows support.",
  "type": "object",
  "definitions": {
    "statusIndicatorObject": {
      "$ref": "components/status-indicator-object.schema.json"
    },
    "linkObject": {
      "$ref": "components/link-object.schema.json"
    }
  },
  "properties": {
    "columnDefinitions": {
      "type": "array",
      "description": "Array of column definitions for the table",
      "items": {
        "type": "object",
        "properties": {
          "header": {
            "type": "string",
            "description": "The header text for the column"
          },
          "field": {
            "type": "string",
            "description": "The field name that corresponds to a property in the table items - used to access and display data for this column"
          },
          "type": {
            "type": "string",
            "enum": ["text", "status-indicator", "link"],
            "description": "The column type. 'text' displays plain text values (default behavior). 'status-indicator' expects objects with 'variant' and 'text'. 'link' expects objects with 'href', 'text', and optional 'external', 'variant', 'ariaLabel' properties"
          },
          "editConfig": {
            "type": "object",
            "description": "Configuration for inline editing of this column",
            "properties": {
              "editingCell": {
                "type": "boolean",
                "description": "Boolean to check if field is editable."
              },
              "validation": {
                "type": "string",
                "description": "Regex for validation."
              }
            }
          }
        },
        "required": ["header", "field"]
      }
    },
    "items": {
      "type": "array",
      "description": "Array of data items to display in the table. For status indicator columns, the corresponding field should contain objects with 'variant' and 'text' properties. For link columns, the corresponding field should contain objects with 'href', 'text', and optional 'external', 'variant', 'ariaLabel' properties.",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique identifier for the table item"
          },
          "parentId": {
            "type": ["string", "null"],
            "description": "Optional parent ID for expandable row functionality - must match another item's ID in the same array and cannot reference the same item's ID (no self-referencing)"
          }
        },
        "required": ["id"],
        "additionalProperties": true
      }
    },
    "header": {
      "type": "string",
      "description": "The header text for the table"
    }
  },
  "required": ["columnDefinitions", "items", "header"]
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TableComponentOutput",
  "description": "The output schema of Table Component",
  "type": "object",
  "properties": {
    "id": {
      "type": "string"
    },
    "parentId": {
      "type": ["string", "null"]
    }
  },
  "required": ["id"],
  "additionalProperties": true
}
```

### General Connector component

![General Connector component diagram](media/image36.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GeneralConnector",
  "type": "object",
  "description": "The GeneralConnector component is a common component that allows users to select an existing connector or create a new one if none exist. It provides configuration for a connector type with customizable fields.",
  "properties": {
    "connector": {
      "type": "object",
      "description": "Configuration for a single connector that can be created or selected",
      "properties": {
        "connectorType": {
          "type": "string",
          "description": "The type of connector required (e.g. '.NET', 'AWS', 'VMware'). This is used to identify the connector in the system."
        },
        "title": {
          "type": "string",
          "description": "(Optional) Display title for the connector type shown in the UI. If not provided, connectorType will be used."
        },
        "description": {
          "type": "string",
          "description": "(Optional) Detailed explanation of the connector's purpose and functionality to help users understand when to use it"
        },
        "maxInstances": {
          "type": "integer",
          "description": "Maximum number of connectors of this type that can be created or selected by the user"
        },
        "fields": {
          "type": "array",
          "description": "Configuration for the input fields that should be collected for each connector instance",
          "items": {
            "type": "object",
            "properties": {
              "fieldName": {
                "type": "string",
                "description": "Internal identifier for the field used for data binding and processing"
              },
              "fieldTitle": {
                "type": "string",
                "description": "Display name of the field shown to the user in the UI"
              },
              "fieldDescription": {
                "type": "string",
                "description": "Helpful text explaining the purpose of the field to the user"
              },
              "fieldRequired": {
                "type": "boolean",
                "description": "Indicates whether this field is required to be filled in by the user"
              },
              "fieldInputType": {
                "type": "string",
                "description": "Specifies the input type for this field (e.g. 'text', 'number', 'select', etc.)"
              },
              "fieldValidation": {
                "type": "string",
                "description": "Regular expression pattern used to validate the field input value"
              },
              "defaultValue": {
                "type": "string",
                "description": "Optional default value for the field when creating a new connector"
              }
            }
          }
        }
      },
      "required": ["connectorType", "maxInstances"]
    }
  },
  "required": ["connector"]
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GeneralConnectorHumanOutput",
  "description": "The output schema of General Connector",
  "type": "object",
  "properties": {
    "connectorId": {
      "type": "string"
    }
  },
  "required": ["connectorId"],
  "additionalProperties": false
}
```

### Markdown Renderer component

![Markdown Renderer component diagram](media/image37.png)

Input schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MarkdownRendererComponent",
  "description": "A component for rendering Markdown content with GitHub Flavored Markdown support.",
  "type": "object",
  "properties": {
    "content": {
      "type": "string",
      "description": "The markdown content to render"
    },
    "submitButtonText": {
      "type": "string",
      "description": "Optional text for the submit button"
    }
  },
  "required": ["content"],
  "additionalProperties": false
}
```

Output schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MarkdownRendererComponentOutput",
  "description": "The output schema of Markdown Renderer component",
  "type": "object",
  "properties": {},
  "required": [],
  "additionalProperties": false
}
```

# Reference

- [🚧 WIP] AWS Transform Agent Developer Guide
- [WIP][External][Confidential] AWS Transform Agent Developer Guide

Agent Builder Base Agent SDK readme https://github.com/awslabs/agent-builder-toolkit-aws-transform/blob/main/packages/sdk/README.md

AWS Transform integration with Genesis

- Partner Engagement for Q Transform Platform

| Roles | Used by | Purpose |
| --- | --- | --- |
| AgentCoreExecutionRole | Agent core runtime | Used by agent instance to assume and access AWS Transform primitives and other AWS resources |
| AWSTransformAgentInvokeRole | AWS Transform | Used by AWS Transform service to assume to invoke the agent in agent core |

|  | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 1 |  |  | Admin | Approver | Contributor | ReadOnly |
| 2 | Read | Critical | ✓ | ✓ | ✓ | ✓ |
| 3 | Update | Critical | ✓ | ✓ | ✗ | ✗ |
| 4 | Delete | Critical | ✓ | ✓ | ✗ | ✗ |
|  |  |  |  |  |  |  |
| 5 | Read | Standard | ✓ | ✓ | ✓ | ✓ |
| 6 | Update | Standard | ✓ | ✓ | ✓ | ✗ |
| 7 | Delete | Standard | ✓ | ✓ | ✓ | ✗ |

| Available HITL UI Tasks | Description | Component Schema |
| --- | --- | --- |
| Text input | For gathering free form text from the user. | Text Input component |
| AutoForm | Dynamic form generator component that creates flexible forms. It defines the structure and validation rules for forms with various field types including text inputs, dropdowns, radio buttons, checkboxes, JSON blocks, and file upload. The schema supports extensible field types with built-in validation and allows forms to be configured declaratively, making it easy to generate consistent UI forms across different parts of an application. | Auto Form component |
| File Upload | For allowing customer to upload a file to the agent. The agent has the ability to set the type of file that the customer can input. By default, it allows all extension | File Upload component |
| Table | For displaying static tabular data in the form of table. Nested rows are supported | Table component |
| General Connector | It defines a reusable component schema that allows users to select existing connectors or create new ones. It provides a flexible configuration system where each connector type can have custom input fields with validation, descriptions, and requirements. | General Connector component |
| Markdown Renderer | Renders LLM generated Markdowns. This is view only. Useful for showing textual content information to the user. | Markdown Renderer component |

| Method | Purpose | Context Source |
| --- | --- | --- |
| atx_agent/invoke | Start agent execution | invocationContext |
| atx_agent/healthcheck | Health status | jobMetadata |
| atx_agent/notify | Platform notifications | jobMetadata |
| atx_agent/restore | State restoration | invocationContext |
| atx_agent/stop | Graceful shutdown | jobMetadata |
| message/send | A2A messaging | metadata.ATX_A2A.AgentInitializationContext |
| tasks/get | Task retrieval | metadata.agentInitializationContext |

| Endpoint | Method | Purpose | Usage |
| --- | --- | --- | --- |
| /ping | GET | Health check | Service monitoring |
| /message/send | POST | A2A messaging | Agent-to-agent communication |
| /invocations | POST | Platform notifications | HITL task updates, job status changes |
