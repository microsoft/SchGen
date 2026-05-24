import os
import time
import abc
import base64
import copy
import sys
import torch
import requests
import json

from typing import Dict, Any
from pydantic import BaseModel

if __name__ == "__main__":
    import sys
    # open config file to get the project path
    project_path = os.environ["PROJECT_PATH"]
    sys.path.append(project_path)

project_path = os.environ["PROJECT_PATH"]
sys.path.append(project_path)

from modules.utils.custom_logger import setup_logger

REASONING_LEVEL = "medium"  # can be "low", "medium", "high"

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
    

def prepare_content_with_image(self, text_input: str, images: str | list[str]) -> list[Dict]:
    """
    Prepare the input for the LLM with images.

    :param text_input: Input text prompt
    :param images: Image file path, need to be converted to base64. can be a list of image paths
    :return: List of message content for LLM
    """

    content = [{"type": "text", "text": text_input}]

    image_num = len(images) if isinstance(images, list) else 1

    if image_num == 1:
        image_path = [images]  # Convert to list for consistency
    
    for path in image_path:
        if path and os.path.exists(path):
            # Encode the image to base64
            base64_image  = encode_image(path)
            image_type = path.split(".")[-1]  # Get the image type from the file extension
        else:
            self.logger.error(f"Image file {path} does not exist.")
            return None
    
        content.append(
            {
                "type": "image_url", 
                "image_url": {"url": f"data:image/{image_type};base64,{base64_image}"}
            }
        )


    # message = {"role": "user",
    #             "content": [
    #                 {"type": "text", "text": new_input},
    #                 {
    #                     "type": "image_url", 
    #                     "image_url": {"url": f"data:image/{image_type};base64,{base64_image}"}
    #                 }
    #             ]
    #             }
    
    # If using response API
    # message = {"role": "user",
    #     "content": [
    #         {"type": "input_text", "text": new_input},
    #         {"type": "input_image", "image_url": f"data:image/{image_type};base64,{base64_image}"}
    #     ]
    #     }

    return content


class LLMInterface(abc.ABC):
    """
    Abstract base class for LLM interaction.
    """

    def __init__(self, model_name="gpt-4o-mini"):
        """
        Initialize LLM interface.

        """
        self.model_name = model_name  # Model name for LLM
        self.logger = setup_logger()
        self.client = None

    def dict_to_msg(self, prompt: Dict[str, str]) -> str:
        """
        Format the prompt dictionary into a single string.

        :param prompt: Input text prompt
        :return: Formatted prompt string
        """
        if self.model_name == "o1":
            my_messages = [
                {"role": "user", "content": prompt["system"] + prompt["user"]},
                {
                    "role": "assistant",
                    "content": prompt["assistant"] if "assistant" in prompt else "",
                },
            ]
        else:
            my_messages = [
                {"role": "system", "content": prompt["system"]},
                {
                    "role": "assistant",
                    "content": prompt["assistant"] if "assistant" in prompt else "",
                },
                {"role": "user", "content": prompt["user"]},
            ]
        return my_messages

    def get_structured_output(self, messages, output_schema: type) -> BaseModel:
        """
        Call LLM with structured output requirement.

        """
        try:
            if self.model_name == "o1" and messages[0]["role"] == "system":
                messages[0]["role"] = "user"

            if hasattr(self, "deployment_name"):
                model_str = self.deployment_name
            elif hasattr(self, "model_url"):
                model_str = self.model_url
            else:
                model_str = self.model_name

            completion = self.client.beta.chat.completions.parse(
                model=model_str,
                messages=messages,
                response_format=output_schema,
                # max_tokens=1024 * 10,
                # temperature=0.7
            )

            response = completion.choices[0].message
            if response.parsed:
                # print(response.parsed)
                self.logger.debug(f"get_structured_output() full parsed Response: {response.parsed}")
                return response.parsed
            elif response.refusal:
                # handle refusal
                # print(response.refusal)
                self.logger.warning(f"get_structured_output() refusal Response: {response.refusal}")
                return None

        except Exception as e:
            # Handle edge cases
            if type(e) == openai.LengthFinishReasonError:
                # Retry with a higher max tokens
                print("Too many tokens: ", e)
                pass
            else:
                # Handle other exceptions
                print(e)
                pass

    """
    Concrete implementation of LLM interface using OpenAI's API.
    """

    def call_llm(self, prompt: Dict[str, str], output_schema: type) -> BaseModel:
        """
        Legacy API, keep for compatibility.

        :param prompt: Input text prompt
        :param output_schema: Expected structured output schema (Pydantic model)
        :return: Parsed response as Pydantic model
        """
        my_messages = self.dict_to_msg(prompt)

        # For deepseek models, use the json response then parse the output
        if "deepseek" in self.model_name or "o1" in self.model_name:
            response, data_obj = self.get_json_response(my_messages, output_schema)
            self.logger.debug(f"call_llm() full text Response: {response}")
            return data_obj

        # For other models, use the official API for structured output if available...
        return self.get_structured_output(my_messages, output_schema)
    
    def format_msg_list_str(self, messages: list[Dict[str, Any]]):
        """
        Print the messages in a readable format string. If the content is a image_url, skip the base64 encoding and just print 'image'.
        """
        formatted_messages = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # If content is a list, format each item
                content_str = ", ".join(
                    [f"{item['type']}: {item['text']}" if item["type"] == "text" else f"{item['type']}: image" for item in content]
                )
            elif isinstance(content, str):
                content_str = content
            else:
                content_str = str(content)
            formatted_messages.append(f"{role}: {content_str}")
        
        # return a combined string like "#msg1# user: xxx #msg2# assistant: yyy #"
        for i in range(len(formatted_messages)):
            formatted_messages[i] = f"#msg{i+1}#\n {formatted_messages[i]} #"
        
        return "\n".join(formatted_messages)


    def get_string_response(self, messages: list[Dict]) -> str:
            """
            Get the completion response from OpenRouter API. With Stream ON.
            """
            max_retry = 6
            response = None

            retry_ct = 0
            while True:
                try:
                    # Reasoning models do not use system messages
                    if ("deepseek" in self.model_name or "o1" in self.model_name or "o3" in self.model_name) and messages[0]["role"] == "system":
                        messages[0]["role"] = "user"

                    if hasattr(self, "deployment_name"):
                        model_str = self.deployment_name
                    elif hasattr(self, "model_url"):
                        model_str = self.model_url
                    else:
                        model_str = self.model_name

                    if "o3" not in model_str and "o1" not in model_str and "o4" not in model_str and "gpt-5" not in model_str:
                        completion = self.client.chat.completions.create(
                            model=model_str,
                            messages=messages,
                            temperature=0.7, # bad perf if 1, Temperature is not supported for o3-mini
                            # top_p=0.7,
                            # max_tokens=4096*4 if "deepseek" in self.model_name else 4096*2,
                            stream=True,
                            reasoning_effort=REASONING_LEVEL
                        )
                    else:
                        completion = self.client.chat.completions.create(
                            model=model_str,
                            messages=messages,
                            # temperature=0.7, # O3 has no temperature option
                            # top_p=0.7,
                            # max_tokens=4096*4 if "deepseek" in self.model_name else 4096*2,
                            stream=True,
                            reasoning_effort=REASONING_LEVEL
                        )    

                    # Print partial completion response
                    self.logger.info(f"Streaming {self.model_name} completion response:")
                    response = []
                    reasoning_content = []
                    
                    for chunk in completion:
                        if chunk.choices:
                            delta = chunk.choices[0].delta
                            
                            # Extract reasoning/thinking content if available
                            if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                                reasoning_content.append(delta.reasoning_content)
                            
                            # Extract regular content
                            if delta.content is not None:
                                content = delta.content
                                response.append(content)

                    response_text = "".join(response)
                    reasoning_text = "".join(reasoning_content)
                    
                    # If reasoning exists, prepend it to the response
                    if reasoning_text:
                        response = f"<reasoning>\n{reasoning_text}\n</reasoning>\n\n{response_text}"
                    else:
                        response = response_text
                    break

                except Exception as e:
                    # Handle edge cases
                    if type(e) == openai.LengthFinishReasonError:
                        # Retry with a higher max tokens
                        print("Too many tokens: ", e)
                        pass
                    else:
                        # Handle other exceptions
                        # print(e)
                        self.logger.error(f"Error in response: {e}")

                        self.logger.debug(f"Current messages: {self.format_msg_list_str(messages)}")
                        
                        if "Error code: 400" in str(e): # Bad Request, likely due to too long prompt
                            self.logger.debug("Trying to fix the prompt by cleaning up the message list...")
                            
                            # Clean up the messages to avoid too long prompt
                            if len(messages) > 4:
                                ## Option 1: Local modification, will not affect the original messages
                                # messages = messages[:2] + messages[-2:]  # Keep only the few messages and the last two messages
                                
                                ## Option 2: Clean up the messages in place
                                # Keep first 2 and last 2 messages by direct slice assignment
                                messages[2:-2] = []  # Remove all elements between the first 2 and last 2
                            
                            self.logger.debug(f"Cleaned messages: {self.format_msg_list_str(messages)}")


                    # self.logger.debug(f"Current prompt: \n{messages}")
                
                    retry_ct += 1
                    if retry_ct >= max_retry:
                        self.logger.error(f"Failed to get completion for {self.model_name}")
                        # response = "Error: Failed to get completion response after multiple retries! Should check server liveness."
                        break

                    self.logger.debug(f"waiting for {10 * (2 ** retry_ct)} seconds before retrying...")
                    # Exponential backoff wait and retry
                    wait_time = 10 * (2 ** retry_ct)  # Exponential backoff
                    time.sleep(wait_time)
                    
                    self.logger.warning(f"Retrying completion for {self.model_name}, {max_retry-retry_ct} time left...")

            if response is None:
                self.logger.error(f"Failed to get completion response for {self.model_name} after {max_retry} retries. Exiting...")
            return response
    
    def prepare_input_with_schematic(self, new_input: str, schematic_path: str) -> list[Dict]:
        """
        Prepare the input for the LLM with schematics.

        :param new_input: Input text prompt
        :param schematic_path: schematic file path, need to be converted to base64
        :return: List of messages for LLM
        """

        if schematic_path and os.path.exists(schematic_path):
            # Read the schematic file
            with open(schematic_path, "r") as schematic_file:
                schematic = schematic_file.read()
        else:
            self.logger.error(f"Schematic file {schematic_path} does not exist.")
            return None

        new_input = new_input + """"
        The schematic file is provided as following:\n
        """ + schematic
        message = {"role": "user",
                   "content": [
                       {"type": "text", "text": new_input},
                   ]
                   }

        return [message]

    def prepare_input_with_image(self, new_input: str, image_path: str) -> list[Dict]:
        """
        Prepare the input for the LLM with images.

        :param new_input: Input text prompt
        :param image_path:image file path, need to be converted to base64
        :return: List of messages for LLM
        """

        if image_path and os.path.exists(image_path):
            # Encode the image to base64
            base64_image  = encode_image(image_path)
            image_type = image_path.split(".")[-1]  # Get the image type from the file extension
        else:
            self.logger.error(f"Image file {image_path} does not exist.")
            return None

        message = {"role": "user",
                   "content": [
                       {"type": "text", "text": new_input},
                       {
                           "type": "image_url", 
                            "image_url": {"url": f"data:image/{image_type};base64,{base64_image}"}
                        }
                   ]
                   }

        return [message]
    
    def prepare_input_with_images(self, new_input: str, image_path_list: list[str]) -> list[Dict]:
        """
        Prepare the input for the LLM with images.

        :param new_input: Input text prompt
        :param image_path: list of image file paths, need to be converted to base64
        :return: List of messages for LLM
        """

        image_type = []
        base64_image = []

        for img in image_path_list:
            if not os.path.exists(img):
                self.logger.error(f"Image file {img} does not exist.")
                return None
            else:
                # Encode the image to base64
                base64_image.append(encode_image(img))
                image_type.append(img.split(".")[-1])


        message = {"role": "user",
                   "content": [
                       {"type": "text", "text": new_input},
                       {
                           "type": "image_url", 
                            "image_url": {"url": f"data:image/{image_type[0]};base64,{base64_image[0]}"}
                        }
                   ]
                   }

        for i in range(1, len(image_path_list)):
            message["content"].append(
                {
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/{image_type[i]};base64,{base64_image[i]}"}
                }
            )
        

        return [message]


    def get_json_response_retry(self, messages: list[Dict], schema) -> tuple[str, BaseModel]:

        max_retry = 3

        retry_ct = 0
        response = ""

        while retry_ct < max_retry:
            try:
                response, data_obj = self.get_json_response(messages, schema)
                if data_obj is not None:
                    return response, data_obj
                else:
                    self.logger.error("Failed to get valid json response, retrying...")
                    retry_ct += 1
                    time.sleep(1)  # wait before retrying
            except Exception as e:
                self.logger.error(f"Exception occurred: {e}, retrying...")
                retry_ct += 1
                time.sleep(1)
        
        self.logger.warning(f"Failed to get valid json response after {max_retry} retries. Using LLM structured output to parse the response.")

        local_msg = [{
            "role": "user",
            "content": f"Provide a structured output by parsing the following response. \n `{response}`"
        }]

        data_obj = LOCAL_HELPER.get_structured_output(local_msg, schema)

        return response, data_obj


    def get_json_response(self, messages: list[Dict], schema) -> tuple[str, BaseModel]:
        
        # assert that schema is the class of a Pydantic model
        assert issubclass(schema, BaseModel), "Schema must be a Pydantic model class"

        if "deepseek" in self.model_name:
            self.logger.info("Deepseek model detected, using two-stage json output for structured response...")
            # To avoid deepseek only outputs the json, we first get the string response without formatting
            response = self.get_string_response(messages)

            messages.append({"role": "assistant", "content": response })

            messages.append({"role": "user",
                             "content": "Summarize your last response using the following Json format. (format the summary as `json { <key>: <value> ... }`, do not include `defs`, `descriptions`, `required`, only the actual content. Make sure it starts with `json {` and end with `}`. Note that In JSON, you only escape characters like quotes or a backslash itself. You can either remove those extra backslashes or double them to get a literal backslash `\\\\`.)" + \
                             str(schema.model_json_schema())  }) # json of a Pydantic model
            json_response = self.get_string_response(messages)

            # final response is the combined response
            response = response + "\n\n" + json_response

            # first find the last `<\think>` tag and extract the json output after that
            # 1. Find the last occurrence of `<\think>` 
            last_think_index = response.rfind("</think>")  # returns -1 if not found

            # 2. If found, work only with the substring after that tag
            if last_think_index != -1:
                substring = response[last_think_index:]
            else:
                # If the tag isn't there, just search the entire response
                substring = response

            # 3. Find the first `json { ... }` in that substring
            json_output = re.search(r"json\s*({.*})", substring, re.DOTALL)

        else:

            # response = self.get_string_response(messages)
            # self.logger.debug(f"get_json_response() full text Response:\n {response}")

            # messages.append({"role": "assistant", "content": response})

            # messages.append({"role": "user",
            #                     "content": "Summarize your last response using the following Json format. (format the summary as `json { <key>: <value> ... }`, do not include `defs`, `descriptions`, `required`, only the actual content. Make sure it starts with `json {` and end with `}`. Note that In JSON, you only escape characters like quotes or a backslash itself. You can either remove those extra backslashes or double them to get a literal backslash `\\\\`.)" + \
            #                     str(schema.model_json_schema())  })
            

            # append the user message to the messages
            if isinstance(messages[-1]["content"], str) and ("First answer questions above" not in messages[-1]["content"]):
                messages[-1]["content"] = messages[-1]["content"] + \
                    "\n\n### \nFirst answer questions above, then, Summarize the output at the end of your response using the following Json format. (format the summary as `json { <key>: <value> ... }`, do not include `defs`, `descriptions`, `required`, only the actual content. Make sure it starts with `json {`. Note that In JSON, you only escape characters like quotes or a backslash itself. You can either remove those extra backslashes or double them to get a literal backslash `\\\\`. If you want to have quotes for string, like \"xxx\", you need three backslash before the quote, like `\\\\\\\"`)" + \
                    str(schema.model_json_schema()) # json of a Pydantic model
            elif isinstance(messages[-1]["content"], list) and ("First answer questions above" not in str(messages[-1]["content"][-1])):
                json_prompt = \
                    "### \nFirst answer questions above, then, Summarize the output at the end of your response using the following Json format. (format the summary as `json { <key>: <value> ... }`, do not include `defs`, `descriptions`, `required`, only the actual content. Make sure it starts with `json {`. Note that In JSON, you only escape characters like quotes or a backslash itself. You can either remove those extra backslashes or double them to get a literal backslash `\\\\`. If you want to have quotes for string, like \"xxx\", you need three backslash before the quote, like `\\\\\\\"`)" + \
                    str(schema.model_json_schema()) # json of a Pydantic model
                messages[-1]["content"].append({"type": "text", "text": json_prompt})
            
            response = self.get_string_response(messages)
            self.logger.debug(f"get_json_response() text + json format Response:\n {response}")

            # Extract the json output from the response, with the first match 
            json_output = re.search(r"json\s*({.*})", response, re.DOTALL)
        

        if json_output:
            # Remove the "json" prefix and any surrounding whitespace or markdown formatting
            json_output = re.sub(r"^```json\s*", "", json_output.group(1))
            json_output = re.sub(r"\s*```$", "", json_output)

            # Remove extra backslashes that are not part of valid JSON escaping
            json_output = json_output.replace("\\\n", "\n")
            try:
                parsed_output = schema.model_validate_json(json_output)
            except Exception as e:
                self.logger.error(f"Failed to validate the json output: {e}")
                # replace single backslashes followed by non-backslash with double backslashes and try again
                # \\ means single backslash in the json string, \\\\ means literal backslash -- because of the way the string is parsed twice
                # json_output =  re.sub(r"([^\\])\\([^\\])", r"\1\\\\\2", json_output)
                json_output = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_output) # Updated regex to avoid single escaping
                try:
                    parsed_output = schema.model_validate_json(json_output)
                except Exception as e:
                    self.logger.error(f"Again, failed to validate the json output: {e}")
                    return response, None
            self.logger.info("Extracted json output from the response")
            return response, parsed_output
        else:
            self.logger.error("Failed to extract json output from the response")
            return response, None


import openai


class OpenAILLMInterface(LLMInterface):
    def __init__(self, model_name="gpt-4o", api_key: str = None):
        super().__init__(model_name)

        # Should read the API key from the environment variable automatically
        # openai.api_key = self.api_key if self.api_key else os.environ.get("OPENAI_API_KEY")

        self.client = openai.OpenAI()

        self.logger.info(f"OpenAI LLM API model name: {model_name}")


def prompt_dict_to_string(prompt: Dict[str, str]) -> str:
    """
    Format the prompt dictionary into a single string.

    :param prompt: Input text prompt
    :return: Formatted prompt string
    """
    return "\n".join([f"{key}: {value}" for key, value in prompt.items()])


from openai import AzureOpenAI
from azure.identity import AzureCliCredential, get_bearer_token_provider
import re


class AzureLLMInterface(LLMInterface):
    def __init__(self, model_name="gpt-4o"):
        super().__init__(model_name)

        scope = "api://trapi/.default"
        credential = get_bearer_token_provider(AzureCliCredential(), scope)

        if self.model_name == "gpt-4o":
            api_version = "2024-10-21"  # Ensure this is a valid API version see: https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-deprecation#latest-ga-api-release
            model_name = "gpt-4o"  # Ensure this is a valid model name https://aka.ms/trapi/models
            model_version = "2024-08-06"  # Ensure this is a valid model version 
        elif self.model_name == "gpt-4o-mini":
            api_version = "2024-10-21"
            model_name = "gpt-4o-mini"
            model_version = "2024-07-18"
        elif self.model_name == "o1":
            api_version = "2024-12-01-preview"
            model_name = "o1"
            model_version = "2024-12-17"
        elif self.model_name == "o3-mini":
            api_version = "2024-12-01-preview"
            model_name = "o3-mini"
            model_version = "2025-01-31"
        elif self.model_name == "o3":
            api_version = "2024-12-01-preview"
            model_name = "o3"
            model_version = "2025-04-16"
        elif self.model_name == "o4-mini":
            api_version = "2024-12-01-preview"
            model_name = "o4-mini"
            model_version = "2025-04-16"
        elif self.model_name == "gpt-5":
            api_version = "2024-12-01-preview"
            model_name = "gpt-5"
            model_version = "2025-08-07"
        elif self.model_name == "gpt-5.1":
            api_version = "2024-12-01-preview"
            model_name = "gpt-5.1"
            model_version = "2025-11-13"
        elif self.model_name == "grok-4":
            api_version = "2025-04-01-preview"
            model_name = "grok-4"
            model_version = "1"
        elif self.model_name == "model-router":
            api_version = "2024-10-21"
            model_name = "model-router"
            model_version = "2025-05-19"
        elif self.model_name == "gpt-4.1":
            api_version = "2025-04-01-preview"
            model_name = "gpt-4.1"
            model_version = "2025-04-14"
        elif self.model_name == "gpt-5.2" :
            api_version = "2024-12-01-preview"
            model_name = "gpt-5.2"
            model_version = "2025-12-11"
        elif self.model_name == "gpt-5.4":
            api_version = "2024-12-01-preview"
            model_name = "gpt-5.4"
            model_version = "2026-03-05"
        elif self.model_name == "gpt-5.4-pro":
            api_version = "2024-12-01-preview"
            model_name = "gpt-5.4-pro"
            model_version = "2026-03-05"
        elif self.model_name == "gpt-5.3-codex":
            api_version = "2024-12-01-preview"
            model_name = "gpt-5.3-codex"
            model_version = "2026-02-24"
        elif self.model_name == "gpt-oss-120b":
            api_version = "2024-12-01-preview"
            model_name = "gpt-oss-120b"
            model_version = "1"
        # Deepseek Series
        elif self.model_name == "DeepSeek-V3.2":
            api_version = "2024-12-01-preview"
            model_name = "DeepSeek-V3.2"
            model_version = "1"
        # Qwen Series
        elif self.model_name == "Qwen3.5-122B-A10B":
            api_version = "2024-12-01-preview"
            model_name = "Qwen/Qwen3.5-122B-A10B"
            model_version = "1"
        else:
            assert False, "Unsupported model name for Azure LLM Interface"

        deployment_name = re.sub(r"[^a-zA-Z0-9_.-]", "", f"{model_name}_{model_version}")  # If your Endpoint doesn't have harmonized deployment names, you can use the deployment name directly: see: https://aka.ms/trapi/models
        self.logger.info(f"Azure LLM Deployment name: {deployment_name}")
        self.deployment_name = deployment_name

        # instance = "msra/shared"  # (or gcr/shared ) See https://aka.ms/trapi/models for the instance name, remove /openai (library adds it implicitly)
        instance = 'gcr/shared'
        endpoint = f"https://trapi.research.microsoft.com/{instance}"

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=credential,
            api_version=api_version,
        )


from langchain_nvidia_ai_endpoints import ChatNVIDIA

class NvidiaLLMInterface(LLMInterface):
    def __init__(self, model_name="deepseek-r1"):
        super().__init__(model_name)

        self.logger.info(f"Nvidia LLM API with model name: {model_name}")

        self.client = openai.OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="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",
        )

        if self.model_name == "deepseek-r1":
            self.model_url = "deepseek-ai/deepseek-r1"
        else:
            assert False, "Unsupported model name for Nvidia LLM Interface"

        # Alternatively, use the ChatNVIDIA class directly
        self.client_nv = ChatNVIDIA(
            model=self.model_url, 
            api_key="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",
            temperature=0.6,
            top_p=0.7,
            max_tokens=4096*5, ## Default value is only 1024, Deepseek-r1 response can be very long...
        )

    def get_string_response(self, messages: list[Dict]) -> str:
        max_retry = 3

        retry_ct = 0
        while True:
            try:
                if self.model_name == "deepseek-r1" and messages[0]["role"] == "system":
                    messages[0]["role"] = "user"


                completion = self.client_nv.stream(messages)

                self.logger.info(f"Streaming {self.model_name} completion response:")
                response = []
                for chunk in completion: 
                    text = chunk.content
                    print(text, end="")
                    response.append(text)

                response = "".join(response)
                break

            except Exception as e:
                # Handle edge cases
                if type(e) == openai.LengthFinishReasonError:
                    # Retry with a higher max tokens
                    print("Too many tokens: ", e)
                    pass
                else:
                    # Handle other exceptions
                    print(e)
                    pass
            
                retry_ct += 1
                if retry_ct >= max_retry:
                    self.logger.error(f"Failed to get completion for {self.model_name}")
                    response = "".join(response) if isinstance(response, list) else response
                    break
                # Exponential backoff wait and retry
                wait_time = 10 * (2 ** retry_ct)  # Exponential backoff
                time.sleep(wait_time)
                self.logger.warning(f"Retrying completion for {self.model_name}, {max_retry- retry_ct} time left...")
        
        return response



    def get_structured_output(self, messages, output_schema):
        """
        Not supported for Deepseek-r1
        """
        structured_chat = self.client_nv.with_structured_output(output_schema)

        completion = structured_chat.stream(messages)

        self.logger.info(f"Streaming {self.model_name} completion response:")
        response = []
        for chunk in completion: 
            text = chunk.content
            print(text, end="")
            response.append(text)

        response = "".join(response)



class OpenRouterLLMInterface(LLMInterface):
    def __init__(self, model_name="o1"):
        super().__init__(model_name)

        self.logger.info(f"OpenRouter LLM API with model name: {model_name}")

        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="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",
        )

        if self.model_name == "o1":
            self.model_url = "openai/o1"
        elif self.model_name == "gemini-pro":
            self.model_url = "google/gemini-3-pro-preview"
        elif self.model_name == "deepseek" or self.model_name == "deepseek-r1":
            self.model_url = "deepseek/deepseek-r1:free"
        elif self.model_name == "gpt-oss-120b":
            self.model_url = "openai/gpt-oss-120b"
        elif self.model_name == "gpt-oss-20b":
            self.model_url = "openai/gpt-oss-20b"
        elif self.model_name == "o4-mini":
            self.model_url = "openai/o4-mini"
        elif self.model_name == "gpt-5":
            self.model_url = "openai/gpt-5"
        elif self.model_name == "gpt-5.1":
            self.model_url = "openai/gpt-5.1"
        elif self.model_name == "grok-4":
            self.model_url = "x-ai/grok-4"
        else:
            assert False, "Unsupported model name for OpenRouter LLM Interface"

    def get_string_response(self, messages: list[Dict]) -> str:
        """
        Get the completion response from OpenRouter API. With Stream ON.
        """
        max_retry = 3

        retry_ct = 0
        while True:
            try:
                # Reasoning models do not use system messages
                if ("deepseek" in self.model_name or "o1" in self.model_name or "o3" in self.model_name) and messages[0]["role"] == "system":
                    messages[0]["role"] = "user"

                completion = self.client.chat.completions.create(
                    model=self.model_url,
                    messages=messages,
                    temperature=0.7, # bad perf if 1
                    # top_p=0.7,
                    max_tokens=4096*4 if "deepseek" in self.model_name else 4096*2,
                    stream=True,
                    reasoning_effort=REASONING_LEVEL
                )

                # Print partial completion response
                self.logger.info(f"Streaming {self.model_name} completion response:")
                response = []
                for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        if content is None:
                            print(chunk.choices[0].delta)
                        response.append(content)
                        print(content, end="")

                response = "".join(response)
                break

            except Exception as e:
                # Handle edge cases
                if type(e) == openai.LengthFinishReasonError:
                    # Retry with a higher max tokens
                    print("Too many tokens: ", e)
                    pass
                else:
                    # Handle other exceptions
                    print(e)
                    pass
            
                retry_ct += 1
                if retry_ct >= max_retry:
                    self.logger.error(f"Failed to get completion for {self.model_name}")
                    break
                # Exponential backoff wait and retry
                wait_time = 10 * (2 ** retry_ct)  # Exponential backoff
                time.sleep(wait_time)
                self.logger.warning(f"Retrying completion for {self.model_name}, {max_retry-retry_ct} time left...")
        
        return response

        # while True:
        #     try:
        #         response = requests.post(
        #         url="https://openrouter.ai/api/v1/chat/completions",
        #         headers={
        #             "Authorization": "Bearer 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",
        #             "Content-Type": "application/json",
        #         },
        #         data=json.dumps({
        #             "model": self.model_url,
        #             "messages": messages,
        #         })
        #         )

        #         break


        #     except Exception as e:
        #         # Handle edge cases
        #         if type(e) == openai.LengthFinishReasonError:
        #             # Retry with a higher max tokens
        #             print("Too many tokens: ", e)
        #             pass
        #         else:
        #             # Handle other exceptions
        #             print(e)
        #             pass
            
        #         retry_ct += 1
        #         if retry_ct >= max_retry:
        #             self.logger.error(f"Failed to get completion for {self.model_name}")
        #             return None
        #         # Exponential backoff wait and retry
        #         wait_time = 10 * (2 ** retry_ct)  # Exponential backoff
        #         time.sleep(wait_time)
        #         self.logger.warning(f"Retrying completion for {self.model_name}, {max_retry-retry_ct} time left...")
    
        # return response.json()["choices"][0]["message"]["content"]

from transformers import AutoModelForCausalLM, AutoTokenizer, Mxfp4Config
# Warning: This class is only used for local LLM generation, check your machine before calling it.
class Local_GPT_oss_Interface(LLMInterface):

    def __init__(self, model_name="gpt-oss-120b"):
        super().__init__(model_name)
        
        self.logger.info(f"Now using Local LLM of model {model_name}.")

        if self.model_name == "gpt-oss-20b":
            self.model_url = "openai/gpt-oss-20b"
        elif self.model_name == "gpt-oss-120b":
            self.model_url = "openai/gpt-oss-120b"
        else:
            assert False, "Unsupported model name for local LLM interface"

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_url)

        quantization_config = Mxfp4Config(dequantize=True)
        model_kwargs = dict(
            attn_implementation="eager",
            torch_dtype=torch.bfloat16,
            quantization_config=quantization_config,
            use_cache=True,
            device_map="auto",
        )

        self.model = AutoModelForCausalLM.from_pretrained(self.model_url, **model_kwargs)

    def get_string_response(self, messages: list[Dict]) -> str:
        """
        Get the completion response from OpenRouter API. With Stream ON.
        """
        max_retry = 3
        retry_ct = 0
        while True:
            try:

                inputs = self.tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    return_tensors="pt",
                    return_dict=True,
                ).to(self.model.device)
                
                generated = self.model.generate(**inputs,
                                                 max_new_tokens=2048,
                                                 do_sample = False,
                                                 repetition_penalty=1.05,
                                                 no_repeat_ngram_size=6
                                                 )
                response = self.tokenizer.decode(generated[0][inputs["input_ids"].shape[-1] :])
                break
                

            except Exception as e:
                # Handle edge cases
                if type(e) == openai.LengthFinishReasonError:
                    # Retry with a higher max tokens
                    print("Too many tokens: ", e)
                    pass
                else:
                    # Handle other exceptions
                    print(e)
                    pass
            
                retry_ct += 1
                if retry_ct >= max_retry:
                    self.logger.error(f"Failed to get completion for {self.model_name}")
                    break
                # Exponential backoff wait and retry
                wait_time = 10 * (2 ** retry_ct)  # Exponential backoff
                time.sleep(wait_time)
                self.logger.warning(f"Retrying completion for {self.model_name}, {max_retry-retry_ct} time left...")
        
        return response

# A generic LLM API for all API providers. We can switch between OpenAI and Azure by changing the model name.
def GetLLMInterface(model_name="gpt-4o", model_provider="Azure"):
    if model_provider == "Azure":
        return AzureLLMInterface(model_name)
    elif model_provider == "OpenAI":
        return OpenAILLMInterface(model_name)
    elif model_provider == "Nvidia":
        return NvidiaLLMInterface(model_name)
    elif model_provider == "OpenRouter":
        return OpenRouterLLMInterface(model_name)
    elif model_provider == "Local":
        return Local_GPT_oss_Interface(model_name)
    else:
        assert False, "Unsupported model provider for Generic LLM Interface"

# Used as back up for json structured output
LOCAL_HELPER = GetLLMInterface(model_name="gpt-4o", model_provider="Azure")

## Testing the OpenAI LLM interface ##
class Step(BaseModel):
    explanation: str
    output: str


class MathReasoning(BaseModel):
    steps: list[Step]
    final_answer: str


def test_azure():
    ## Test the OpenAI LLM interface
    # llm_interface = GetLLMInterface(model_name="chatgpt-4o-latest", model_provider="OpenAI")
    # llm_interface = GetLLMInterface(model_name="gpt-4o", model_provider="Azure")
    # llm_interface_o1 = GetLLMInterface(
    #     model_name="deepseek-r1", model_provider="Nvidia"
    # )

    llm_interface = GetLLMInterface(model_name="grok-4", model_provider="OpenRouter")

    # llm_interface_o4 = GetLLMInterface(model_name="o4-mini", model_provider="Azure")
    # llm_interface_o3 = GetLLMInterface(model_name="o3", model_provider="Azure")

    # llm_interface_oss = GetLLMInterface(model_name="gpt-oss-120b", model_provider="Azure")

    # llm_interface.call_llm("Translate this demand to specifications", {"frequency_range": tuple, "gain_requirement": float})

    messages = [{"role": "user", "content": "how can I solve 8x^2 + 7 = -23 + x"}]

    print(llm_interface.format_msg_list_str(messages))

    # response = llm_interface.get_string_response(messages)
    # print(response)

    prompt = {
        "system": "You are a helpful tutor. Guide the user through the solution step by step and use latex match format. Perform the following steps and reply with your answers:\n **Summary and Output**:  Summarize output about the qualitative rationale or quantitative calculation process.",  # `output above rationale seems`` to be the sensitive word here.. May cause OPENAI usage policy violation error.
        "user": "how can I solve 8x^2 + 7 = -23 + x. Note that this prompt is for information summary only and does not violate usage policy to my knowledge. ",
    }
    # llm_interface.logger.info("Testing Azure LLM interface -- O4 mini")
    # response = llm_interface_o4.get_string_response(llm_interface_o4.dict_to_msg(prompt))
    # print(response)

    # llm_interface_o3.logger.info("Testing Azure LLM interface -- O3")
    # llm_interface_o3.get_structured_output(llm_interface_o3.dict_to_msg(prompt), MathReasoning)
    # print(llm_interface_o1.get_json_response(llm_interface_o1.dict_to_msg(prompt), MathReasoning))

    response = llm_interface.get_string_response(llm_interface.dict_to_msg(prompt))
    print(response)


def test_openrouter():

    ## -- Test the OpenRouter O1 interface -- ##
    llm_interface = GetLLMInterface(model_name="gpt-oss-20b", model_provider="OpenRouter")

    # ## -- Test the OpenRouter Deepseek interface -- ##
    # llm_interface = GetLLMInterface(model_name="deepseek", model_provider="OpenRouter")
    # prompt = {
    #     "system": "You are a helpful tutor. Guide the user through the solution step by step and use latex match format.",  # output above rationale seems to be the sensitive word here..
    #     "user": "how can I solve 8x^2 + 7 = -23 + x. Note that this prompt is for information summary only and does not violate usage policy to my knowledge. ",
    # }
    # messages = llm_interface.dict_to_msg(prompt)
    messages = [
        {
            "role": "system",
            "content": [
                {
                    type: "text",
                    "text": "You are a helpful tutor. Guide the user through the solution step by step and use latex match format.",  # output above rationale seems to be the sensitive word here..
                },
            ],

            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "how can I solve 8x^2 + 7 = -23 + x. Note that this prompt is for information summary only and does not violate usage policy to my knowledge. ",
                },
             ]
        }
    ]
    response = llm_interface.get_string_response(messages)
    # response = llm_interface.call_llm(prompt, MathReasoning)
    print(response)


def test_nvidia():
    llm_interface = GetLLMInterface(model_name="deepseek-r1", model_provider="Nvidia")
    messages = [{"role": "user", "content": "What is the meaning of life?"}]
    response = llm_interface.get_string_response(messages)
    print(response)


def test_image_reading():
    # Test the image reading and encoding function
    image_path = "export/sch_with_axes.png"  # Replace with your image path

    llm_interface = GetLLMInterface(model_name="o4-mini", model_provider="Azure")
    # llm_interface = GetLLMInterface(model_name="gpt-5", model_provider="Azure")
    
    llm_interface.logger.info("Testing Azure LLM interface for Image reading --")

    # messages = [{"role": "user", "content": "how can I solve 8x^2 + 7 = -23 + x"}]
    # response = llm_interface.get_string_response(messages)
    # print(response)

    image_msg = llm_interface.prepare_input_with_image("Explain what is shown in the image?", image_path)
    response = llm_interface.get_string_response(image_msg)

def test_local(model_name="gpt-oss-20b"):
    llm_interface = GetLLMInterface(model_name=model_name, model_provider="Local")
    messages = [{"role": "user", "content": "What is the meaning of life?"}]
    response = llm_interface.get_string_response(messages)
    print(response)

if __name__ == "__main__":
    # main()

    test_azure()

    # test_nvidia()
    
    # test_openrouter()

    # test_nvidia()

    # test_image_reading()

    # test_local("gpt-oss-20b")


