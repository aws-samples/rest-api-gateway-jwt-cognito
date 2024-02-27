import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigw from 'aws-cdk-lib/aws-apigateway';

import path = require("path");

export class RestApiGatewayJwtCognitoStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // create Cognito UserPool
    const userPool = new cognito.UserPool(this, "UserPool", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // create and add Application Integration for the User Pool
    // and add support for oAuth / JWT tokens
    const appIntegrationClient = userPool.addClient("WebClient", {
      userPoolClientName: "MyAppWebClient",
      idTokenValidity: cdk.Duration.days(1),
      accessTokenValidity: cdk.Duration.days(1),
      authFlows: {
        adminUserPassword: true
      },
      oAuth: {
        flows: {authorizationCodeGrant: true},
        scopes: [cognito.OAuthScope.OPENID]
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO]
    });

    // create a Lambda function for API Gateway to invoke
    const lambdaFn = new lambda.Function(this, "lambdaFn", {
      code: lambda.Code.fromAsset(path.join(__dirname, "../lambda/simple-function")),
      runtime: lambda.Runtime.PYTHON_3_11,
      timeout: cdk.Duration.seconds(40),
      handler: "lambda_function.lambda_handler",
    });

    // API Gateway Definition
    const restApi = new apigw.RestApi(this, "RestAPI", {
      restApiName: "simpleRestAPI",
    });

    // capturing architecture for docker container (arm or x86)
    const dockerPlatform = process.env["DOCKER_CONTAINER_PLATFORM_ARCH"]

    // Authorizer function for JWT tokens
    const dockerfile = path.join(__dirname, "../lambda/dockerized-jwt-auth-function/");
    const code = lambda.Code.fromAssetImage(dockerfile);
    const jwtAuthLayeredFn = new lambda.Function(this, "jwtAuthLayeredFn", {
      code: code,
      handler: lambda.Handler.FROM_IMAGE,
      runtime: lambda.Runtime.FROM_IMAGE,
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      architecture: dockerPlatform == "arm" ? lambda.Architecture.ARM_64 : lambda.Architecture.X86_64,
      environment: {
          "API_ID": restApi.restApiId,
          "API_REGION": this.region,
          "ACCOUNT_ID": this.account,
          "COGNITO_USER_POOL_ID": userPool.userPoolId,
          "COGNITO_APP_CLIENT_ID": appIntegrationClient.userPoolClientId    
      }
    });

    // create JWT token authorizer for the API Gateway endpoint
    const tokenAuthorizer = new apigw.TokenAuthorizer(this, 'jwttokenAuth', {
      handler: jwtAuthLayeredFn,
      validationRegex: "^(Bearer )[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)$"
      });

    // create a GET /hello endpoint which invoked the simple lambda function,
    // and uses the token authorizer created above
    const helloEndpoint = restApi.root.addResource('hello');
    helloEndpoint.addMethod(
      "GET", 
      new apigw.LambdaIntegration(lambdaFn),
      { authorizer: tokenAuthorizer }
    );

  }
}
