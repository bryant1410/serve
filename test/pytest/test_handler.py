import ast
import json
import logging
import os

import numpy as np
import pytest
import requests
import test_utils
import torch

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../")
)
snapshot_file_kf = os.path.join(REPO_ROOT, "test", "config_kf.properties")
snapshot_file_tf = os.path.join(REPO_ROOT, "test", "config_ts.properties")
data_file_mnist = os.path.join(
    REPO_ROOT, "examples", "image_classifier", "mnist", "test_data", "1.png"
)
input_json_mnist = os.path.join(
    REPO_ROOT, "kubernetes", "kserve", "kf_request_json", "v1", "mnist.json"
)
input_json_mmf = os.path.join(
    REPO_ROOT, "examples", "MMF-activity-recognition", "372CC.info.json"
)
logger = logging.getLogger(__name__)


def getAPIS(snapshot_file):
    MANAGEMENT_API = "http://127.0.0.1:8081"
    INFERENCE_API = "http://127.0.0.1:8080"

    with open(snapshot_file, "r") as fp:
        lines = fp.readlines()
    for line in lines:
        line = line.rstrip("\n")
        if "management_address" in line:
            MANAGEMENT_API = line.split("=")[1]
        if "inference_address" in line:
            INFERENCE_API = line.split("=")[1]

    return (MANAGEMENT_API, INFERENCE_API)


KF_MANAGEMENT_API, KF_INFERENCE_API = getAPIS(snapshot_file_kf)
TF_MANAGEMENT_API, TF_INFERENCE_API = getAPIS(snapshot_file_tf)


def setup_module(module):
    test_utils.torchserve_cleanup()
    response = requests.get(
        "https://torchserve.pytorch.org/mar_files/mnist.mar", allow_redirects=True
    )
    with open(os.path.join(test_utils.MODEL_STORE, "mnist.mar"), "wb") as f:
        f.write(response.content)


def teardown_module(module):
    test_utils.torchserve_cleanup()


def mnist_model_register_using_non_existent_handler_then_scale_up(synchronous=False):
    """
    Validates that snapshot.cfg is created when management apis are invoked.
    """
    response = requests.post(
        TF_MANAGEMENT_API + "/models?handler=nehandler&url=mnist.mar"
    )

    # Scale up workers
    if synchronous:
        params = (
            ("min_worker", "2"),
            ("synchronous", "True"),
        )
    else:
        params = (("min_worker", "2"),)

    response = requests.put(TF_MANAGEMENT_API + "/models/mnist", params=params)
    # Check if workers got scaled
    response = requests.get(TF_MANAGEMENT_API + "/models/mnist")
    return response


def mnist_model_register_and_scale_using_non_existent_handler_synchronous():
    # Register & Scale model
    response = mnist_model_register_using_non_existent_handler_then_scale_up(
        synchronous=True
    )
    mnist_list = json.loads(response.content)
    try:
        # Workers should not scale up
        assert len(mnist_list[0]["workers"]) == 0
    finally:
        # UnRegister mnist model
        test_utils.unregister_model("mnist")


def mnist_model_register_and_scale_using_non_existent_handler_asynchronous():
    # Register & Scale model
    response = mnist_model_register_using_non_existent_handler_then_scale_up()
    mnist_list = json.loads(response.content)
    try:
        # Workers should not scale up
        assert len(mnist_list[0]["workers"]) == 0
    finally:
        # UnRegister mnist model
        test_utils.unregister_model("mnist")


def run_inference_using_url_with_data(purl=None, pfiles=None, ptimeout=120):
    print(f"purl={purl}")
    print(f"pfiles={pfiles}")
    if purl is None and pfiles is None:
        return
    print(f"purl1={purl}")
    print(f"pfiles1={pfiles}")
    try:
        response = requests.post(url=purl, files=pfiles, timeout=ptimeout)
    except:
        print(f"sent echo_stream rep=none")
        return None
    else:
        print(f"sent echo_stream rep={response}")
        return response


def run_inference_using_url_with_data_json(purl=None, json_input=None, ptimeout=120):
    if purl is None and pfiles is None:
        return
    try:
        response = requests.post(url=purl, json=json_input, timeout=ptimeout)
    except:
        return None
    else:
        return response


def test_mnist_model_register_and_inference_on_valid_model():
    """
    Validates that snapshot.cfg is created when management apis are invoked.
    """
    test_utils.start_torchserve(no_config_snapshots=True)
    test_utils.register_model("mnist", "mnist.mar")
    files = {
        "data": (data_file_mnist, open(data_file_mnist, "rb")),
    }
    response = run_inference_using_url_with_data(
        TF_INFERENCE_API + "/predictions/mnist", files
    )

    assert (json.loads(response.content)) == 1
    test_utils.unregister_model("mnist")


def test_mnist_model_register_using_non_existent_handler_with_nonzero_workers():
    """
    Validates that a model cannot be registered with a non existent handler if
    the initial number of workers is greater than zero.
    """

    response = requests.post(
        TF_MANAGEMENT_API
        + "/models?handler=nehandlermodels&initial_workers=1&url=mnist.mar"
    )
    if (
        json.loads(response.content)["code"] == 500
        and json.loads(response.content)["type"] == "InternalServerException"
    ):
        assert True, (
            "Internal Server Exception, "
            "Cannot register model with non existent handler with non zero workers"
        )
    else:
        assert False, (
            "Something is not right!! Successfully registered model with "
            "non existent handler with non zero workers"
        )

    test_utils.unregister_model("mnist")


def test_mnist_model_register_scale_inference_with_non_existent_handler():
    response = mnist_model_register_using_non_existent_handler_then_scale_up()
    mnist_list = json.loads(response.content)
    assert len(mnist_list[0]["workers"]) > 1
    files = {
        "data": (data_file_mnist, open(data_file_mnist, "rb")),
    }

    response = run_inference_using_url_with_data(
        TF_INFERENCE_API + "/predictions/mnist", files
    )
    if response is None:
        assert True, "Inference failed as the handler is non existent"
    else:
        if json.loads(response.content) == 1:
            assert False, (
                "Something is not right!! Somehow Inference passed "
                "despite passing non existent handler"
            )


def test_mnist_model_register_and_inference_on_valid_model_explain():
    """
    Validates that snapshot.cfg is created when management apis are invoked.
    """
    test_utils.start_torchserve(no_config_snapshots=True)
    test_utils.register_model("mnist", "mnist.mar")
    files = {
        "data": (data_file_mnist, open(data_file_mnist, "rb")),
    }
    response = run_inference_using_url_with_data(
        TF_INFERENCE_API + "/explanations/mnist", files
    )

    assert np.array(json.loads(response.content)).shape == (1, 28, 28)
    test_utils.unregister_model("mnist")


def test_kserve_mnist_model_register_and_inference_on_valid_model():
    """
    Validates that snapshot.cfg is created when management apis are invoked for kserve.
    """
    test_utils.start_torchserve(snapshot_file=snapshot_file_kf)
    test_utils.register_model("mnist", "mnist.mar")

    with open(input_json_mnist, "r") as f:
        s = f.read()
        s = s.replace("'", '"')
        data = json.loads(s)

    response = run_inference_using_url_with_data_json(
        KF_INFERENCE_API + "/v1/models/mnist:predict", data
    )

    assert (json.loads(response.content)["predictions"][0]) == 2
    test_utils.unregister_model("mnist")


def test_kserve_mnist_model_register_scale_inference_with_non_existent_handler():
    response = mnist_model_register_using_non_existent_handler_then_scale_up()
    mnist_list = json.loads(response.content)
    assert len(mnist_list[0]["workers"]) > 1
    with open(input_json_mnist, "r") as f:
        s = f.read()
        s = s.replace("'", '"')
        data = json.loads(s)

    response = run_inference_using_url_with_data_json(
        KF_INFERENCE_API + "/v1/models/mnist:predict", data
    )

    if response is None:
        assert True, "Inference failed as the handler is non existent"
    else:
        if json.loads(response.content) == 1:
            assert False, (
                "Something is not right!! Somehow Inference passed "
                "despite passing non existent handler"
            )


def test_kserve_mnist_model_register_and_inference_on_valid_model_explain():
    """
    Validates the kserve model explanations.
    """
    test_utils.start_torchserve(snapshot_file=snapshot_file_kf)
    test_utils.register_model("mnist", "mnist.mar")
    with open(input_json_mnist, "r") as f:
        s = f.read()
        s = s.replace("'", '"')
        data = json.loads(s)

    response = run_inference_using_url_with_data_json(
        KF_INFERENCE_API + "/v1/models/mnist:explain", data
    )

    assert np.array(json.loads(response.content)["explanations"]).shape == (
        1,
        1,
        28,
        28,
    )
    test_utils.unregister_model("mnist")


def test_huggingface_bert_batch_inference():
    batch_size = 2
    batch_delay = 10000  # 10 seconds
    params = (
        ("model_name", "BERTSeqClassification"),
        ("url", "https://torchserve.pytorch.org/mar_files/BERTSeqClassification.mar"),
        ("initial_workers", "1"),
        ("batch_size", str(batch_size)),
        ("max_batch_delay", str(batch_delay)),
    )
    test_utils.start_torchserve(no_config_snapshots=True)
    test_utils.register_model_with_params(params)
    input_text = os.path.join(
        REPO_ROOT,
        "examples",
        "Huggingface_Transformers",
        "Seq_classification_artifacts",
        "sample_text.txt",
    )

    # Make 2 curl requests in parallel with &
    # curl --header \"X-Forwarded-For: 1.2.3.4\" won't work since you can't access local host anymore
    response = os.popen(
        f"curl http://127.0.0.1:8080/predictions/BERTSeqClassification -T {input_text} & curl http://127.0.0.1:8080/predictions/BERTSeqClassification -T {input_text}"
    )
    response = response.read()

    ## Assert that 2 responses are returned from the same batch
    assert response == "Not AcceptedNot Accepted"
    test_utils.unregister_model("BERTSeqClassification")


@pytest.mark.skip(reason="MMF doesn't support PT 1.10 yet")
def test_MMF_activity_recognition_model_register_and_inference_on_valid_model():
    test_utils.start_torchserve(snapshot_file=snapshot_file_tf)
    test_utils.register_model(
        "MMF_activity_recognition_v2",
        "https://torchserve.pytorch.org/mar_files/MMF_activity_recognition_v2.mar",
    )
    os.system(
        "wget https://mmfartifacts.s3-us-west-2.amazonaws.com/372CC.mp4 -P ../../examples/MMF-activity-recognition"
    )
    input_json = "../../examples/MMF-activity-recognition/372CC.info.json"
    with open(input_json) as jsonfile:
        info = json.load(jsonfile)

    files = {
        "data": open("../../examples/MMF-activity-recognition/372CC.mp4", "rb"),
        "script": info["script"],
        "labels": info["action_labels"],
    }
    response = run_inference_using_url_with_data(
        TF_INFERENCE_API + "/v1/models/MMF_activity_recognition_v2:predict",
        pfiles=files,
    )
    response = response.content.decode("utf-8")
    response = ast.literal_eval(response)
    response = [n.strip() for n in response]
    assert response == [
        "Sitting at a table",
        "Someone is sneezing",
        "Watching a laptop or something on a laptop",
    ]
    test_utils.unregister_model("MMF_activity_recognition_v2")


def test_huggingface_bert_model_parallel_inference():
    number_of_gpus = torch.cuda.device_count()
    check = os.popen(f"curl http://localhost:8081/models")
    print(check)
    if number_of_gpus > 1:
        batch_size = 1
        batch_delay = 5000  # 10 seconds
        params = (
            ("model_name", "Textgeneration"),
            (
                "url",
                "https://bert-mar-file.s3.us-west-2.amazonaws.com/Textgeneration.mar",
            ),
            ("initial_workers", "1"),
            ("batch_size", str(batch_size)),
            ("max_batch_delay", str(batch_delay)),
        )
        test_utils.start_torchserve(no_config_snapshots=True)
        test_utils.register_model_with_params(params)
        input_text = os.path.join(
            REPO_ROOT,
            "examples",
            "Huggingface_Transformers",
            "Text_gen_artifacts",
            "sample_text_captum_input.txt",
        )

        response = os.popen(
            f"curl http://127.0.0.1:8080/predictions/Textgeneration -T {input_text}"
        )
        response = response.read()

        assert (
            "Bloomberg has decided to publish a new report on the global economy"
            in response
        )
        test_utils.unregister_model("Textgeneration")
    else:
        logger.info(
            "Running model parallel inference requuires more than one gpu, number of available gpus on thi machine is: ",
            number_of_gpus,
        )


def test_huggingface_opt_distributed_inference_deepspeed():
    TORCHSERVE_URL = "https://torchserve.s3.amazonaws.com/mar_files/opt-ds.tar.gz"
    BATCH_SIZE = 1
    BATCH_DELAY = 10000  # 10 seconds
    INPUT_TEXT = os.path.join(
        REPO_ROOT, "examples", "large_models", "deepspeed", "opt", "sample_text.txt"
    )
    number_of_gpus = torch.cuda.device_count()
    logger.info(f"Number of available GPUs on this machine: {number_of_gpus}")
    if number_of_gpus > 1:
        try:
            with os.popen(f"curl http://localhost:8081/models") as check:
                logger.debug(
                    f"Check if any model is already registered: {check.read()}"
                )

            params = (
                ("model_name", "opt"),
                ("url", TORCHSERVE_URL),
                ("initial_workers", "1"),
                ("batch_size", str(BATCH_SIZE)),
                ("max_batch_delay", str(BATCH_DELAY)),
            )
            test_utils.start_torchserve(no_config_snapshots=True)
            test_utils.register_model_with_params(params)

            with os.popen(
                f"curl http://127.0.0.1:8080/predictions/opt -T {INPUT_TEXT}"
            ) as response:
                response_text = response.read()

            assert (
                "Today the weather is really nice and I am planning on\n\n\nI am planning on the next day.\n\nI am planning on the next day.\n\nI am planning on the next day.\nI am planning on the next"
                in response_text
            ), "Incorrect response from model"
        finally:
            test_utils.unregister_model("opt")
    else:
        logger.warning("Running distributed inference requires more than one GPU.")


def test_echo_stream_inference():
    test_utils.start_torchserve(no_config_snapshots=True, gen_mar=False)
    test_utils.register_model(
        "echo_stream", "https://torchserve.pytorch.org/mar_files/echo_stream.mar"
    )

    response = requests.post(
        TF_INFERENCE_API + "/predictions/echo_stream", data="foo", stream=True
    )
    assert response.headers["Transfer-Encoding"] == "chunked"

    prediction = []
    for chunk in response.iter_content(chunk_size=None):
        if chunk:
            prediction.append(chunk.decode("utf-8"))

    assert str(" ".join(prediction)) == "hello hello hello hello world "
    test_utils.unregister_model("echo_stream")