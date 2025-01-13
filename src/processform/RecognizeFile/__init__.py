# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from dataclasses import field
import logging
import json
import os
import uuid
import azure.functions as func
from azure.storage.blob import BlobClient
from azure.identity import DefaultAzureCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # Initialize variables to avoid UnboundLocalError
    output_data_json = None

    try:
        # Parse the request body
        req_body = req.get_json()

        # Extract required fields
        storage_account = req_body.get('storage_account')
        input_container = req_body.get('input_container')
        output_container = req_body.get('output_container')
        file_name = req_body.get('file_name')
        file_path = req_body.get('file_path')
        date_time = req_body.get('date_time')
        date_only = req_body.get('date')
        year_number = req_body.get('year')
        month_number = req_body.get('month')
        day_number = req_body.get('day')

        # Validate required fields
        if not (storage_account and input_container and output_container and
                file_name and file_path and date_time and year_number and 
                month_number and day_number):
            http_body_msg = f"Not all required fields are present in request."
            return func.HttpResponse(body=http_body_msg, status_code=400)  # 400 Bad Request

        # Build blob storage URLs
        my_account_url = f"https://{storage_account}.blob.core.windows.net"
        input_blob_url = f"{my_account_url}{file_path}"  # Preferred method 

        # Managed Identity
        client_id = os.getenv("RG_MID_CLIENT_ID")
        my_credential = DefaultAzureCredential(managed_identity_client_id=client_id)

        # Form Recognizer configuration
        fr_endpoint = os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
        apim_key = os.getenv("AZURE_FORM_RECOGNIZER_KEY")

        logging.info(f"Endpoint: {fr_endpoint}")

        # Form Recognizer client
        document_analysis_client = DocumentAnalysisClient(
            endpoint=fr_endpoint, credential=AzureKeyCredential(apim_key))

        # Analyze document with the prebuilt Read model
        poller = document_analysis_client.begin_recognize_content_from_url(document_url=input_blob_url)
        analyzedResult = poller.result()

        logging.info("Form Recognizer Read model analyzed successfully.")

        # Process Form Recognizer output
        page_results = []
        uuid_str = str(uuid.uuid4())

        for page in analyzedResult.pages:
            page_data = {
                'page_number': page.page_number,
                'width': page.width,
                'height': page.height,
                'unit': page.unit
            }
            page_results.append(page_data)

        output_data = {
            'id': uuid_str,
            'date_time': date_time,
            'date': date_only,
            'year': year_number,
            'month': month_number,
            'day': day_number,
            'file_name': file_name,
            'file_path': file_path,
            'page_results': page_results
        }

        output_data_json = json.dumps(output_data)

        # Upload to Azure Storage
        base_name = os.path.basename(file_path)
        ext_split = os.path.splitext(base_name)
        file_name_no_ext = ext_split[0]

        dir_name = f"{year_number}/{month_number}/{day_number}"
        output_file_path_no_container = f"/{dir_name}/{file_name_no_ext}_read_output.json"
        output_blob_client = BlobClient(
            account_url=my_account_url,
            container_name=output_container,
            blob_name=output_file_path_no_container,
            credential=my_credential
        )
        output_blob_client.upload_blob(output_data_json, overwrite=True, blob_type="BlockBlob")

    except Exception as ex_main:
        logging.error(f"Exception occurred: {ex_main}")
        return func.HttpResponse(body=f"Error processing the request: {ex_main}", status_code=500)  # 500 Internal Server Error

    logging.info("Processing successful. Returning output.")
    return func.HttpResponse(body=output_data_json, status_code=200)
