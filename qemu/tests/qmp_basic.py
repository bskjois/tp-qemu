from virttest import utils_misc

try:
    unicode
except NameError:
    unicode = str


def run(test, params, env):
    """
    QMP Specification test-suite: this checks if the *basic* protocol conforms
    to its specification, which is file QMP/qmp-spec.txt in QEMU's source tree.

    IMPORTANT NOTES:

        o Most tests depend heavily on QMP's error information (eg. classes),
          this might have bad implications as the error interface is going to
          change in QMP

        o Command testing is *not* covered in this suite. Each command has its
          own specification and should be tested separately

        o We use the same terminology as used by the QMP specification,
          specially with regard to JSON types (eg. a Python dict is called
          a json-object)

        o This is divided in sub test-suites, please check the bottom of this
          file to check the order in which they are run

    TODO:

        o Finding which test failed is not as easy as it should be

        o Are all those check_*() functions really needed? Wouldn't a
          specialized class (eg. a Response class) do better?
    """

    def fail_no_key(qmp_dict, key):
        if not isinstance(qmp_dict, dict):
            test.fail("qmp_dict is not a dict (it's '%s')" % type(qmp_dict))
        if key not in qmp_dict:
            test.fail("'%s' key doesn't exist in dict ('%s')" % (key, str(qmp_dict)))

    def check_dict_key(qmp_dict, key, keytype):
        """
        Performs the following checks on a QMP dict key:

        1. qmp_dict is a dict
        2. key exists in qmp_dict
        3. key is of type keytype

        If any of these checks fails, error.TestFail is raised.
        """
        fail_no_key(qmp_dict, key)
        if not isinstance(qmp_dict[key], keytype):
            test.fail(
                "'%s' key is not of type '%s', it's '%s'"
                % (key, keytype, type(qmp_dict[key]))
            )

    def check_key_is_dict(qmp_dict, key):
        check_dict_key(qmp_dict, key, dict)

    def check_key_is_list(qmp_dict, key):
        check_dict_key(qmp_dict, key, list)

    def check_key_is_str(qmp_dict, key):
        check_dict_key(qmp_dict, key, unicode)

    def check_str_key(qmp_dict, keyname, value=None):
        check_dict_key(qmp_dict, keyname, unicode)
        if value and value != qmp_dict[keyname]:
            test.fail(
                "'%s' key value '%s' should be '%s'"
                % (keyname, str(qmp_dict[keyname]), str(value))
            )

    def check_key_is_int(qmp_dict, key):
        fail_no_key(qmp_dict, key)
        try:
            int(qmp_dict[key])
        except Exception:
            test.fail(
                "'%s' key is not of type int, it's '%s'" % (key, type(qmp_dict[key]))
            )

    def check_bool_key(qmp_dict, keyname, value=None):
        check_dict_key(qmp_dict, keyname, bool)
        if value and value != qmp_dict[keyname]:
            test.fail(
                "'%s' key value '%s' should be '%s'"
                % (keyname, str(qmp_dict[keyname]), str(value))
            )

    def check_success_resp(resp, empty=False):
        """
        Check QMP OK response.

        :param resp: QMP response
        :param empty: if True, response should not contain data to return
        """
        check_key_is_dict(resp, "return")
        if empty and len(resp["return"]) > 0:
            test.fail("success response is not empty ('%s')" % str(resp))

    def check_error_resp(resp, classname=None, datadict=None):
        """
        Check QMP error response.

        :param resp: QMP response
        :param classname: Expected error class name
        :param datadict: Expected error data dictionary
        """
        check_key_is_dict(resp, "error")
        check_key_is_str(resp["error"], "class")
        if classname and resp["error"]["class"] != classname:
            test.fail(
                "got error class '%s' expected '%s'"
                % (resp["error"]["class"], classname)
            )
        if datadict and resp["error"]["desc"] != datadict:
            test.fail(
                "got error desc '%s' expected '%s'" % (resp["error"]["desc"], datadict)
            )

    def test_version(version):
        """
        Check the QMP greeting message version key which, according to QMP's
        documentation, should be:

        { "qemu": { "major": json-int, "minor": json-int, "micro": json-int }
          "package": json-string }
        """
        check_key_is_dict(version, "qemu")
        for key in ("major", "minor", "micro"):
            check_key_is_int(version["qemu"], key)
        check_key_is_str(version, "package")

    def test_greeting(greeting):
        check_key_is_dict(greeting, "QMP")
        check_key_is_dict(greeting["QMP"], "version")
        check_key_is_list(greeting["QMP"], "capabilities")

    def greeting_suite(monitor):
        """
        Check the greeting message format, as described in the QMP
        specfication section '2.2 Server Greeting'.

        { "QMP": { "version": json-object, "capabilities": json-array } }
        """
        greeting = monitor.get_greeting()
        test_greeting(greeting)
        test_version(greeting["QMP"]["version"])

    def json_parsing_errors_suite(monitor):
        """
        Check that QMP's parser is able to recover from parsing errors, please
        check the JSON spec for more info on the JSON syntax (RFC 4627).
        """
        # We're quite simple right now and the focus is on parsing errors that
        # have already biten us in the past.
        #
        # TODO: The following test-cases are missing:
        #
        #   - JSON numbers, strings and arrays
        #   - More invalid characters or malformed structures
        #   - Valid, but not obvious syntax, like zillion of spaces or
        #     strings with unicode chars (different suite maybe?)
        bad_json = []

        # A JSON value MUST be an object, array, number, string, true, false,
        # or null
        #
        # NOTE: QMP seems to ignore a number of chars, like: | and ?
        bad_json.append(":")
        bad_json.append(",")

        # Malformed json-objects
        #
        # NOTE: sending only "}" seems to break QMP
        # NOTE: Duplicate keys are accepted (should it?)
        bad_json.append('{ "execute" }')
        bad_json.append('{ "execute": "query-version", }')
        bad_json.append('{ 1: "query-version" }')
        bad_json.append('{ true: "query-version" }')
        bad_json.append('{ []: "query-version" }')
        bad_json.append('{ {}: "query-version" }')

        for cmd in bad_json:
            resp = monitor.cmd_raw(cmd)
            check_error_resp(resp, "GenericError")

    def test_id_key(monitor):
        """
        Check that QMP's "id" key is correctly handled.
        """
        # The "id" key must be echoed back in error responses
        id_key = "virt-test"
        resp = monitor.cmd_qmp("eject", {"foobar": True}, q_id=id_key)
        check_error_resp(resp)
        check_str_key(resp, "id", id_key)

        # The "id" key must be echoed back in success responses
        resp = monitor.cmd_qmp("query-status", q_id=id_key)
        check_success_resp(resp)
        check_str_key(resp, "id", id_key)

        # The "id" key can be any json-object
        for id_key in (
            True,
            1234,
            "string again!",
            [1, [], {}, True, "foo"],
            {"key": {}},
        ):
            resp = monitor.cmd_qmp("query-status", q_id=id_key)
            check_success_resp(resp)
            if resp["id"] != id_key:
                test.fail(
                    "expected id '%s' but got '%s'" % (str(id_key), str(resp["id"]))
                )

    def test_invalid_arg_key(monitor):
        """
        Currently, the only supported keys in the input object are: "execute",
        "arguments" and "id". Although expansion is supported, invalid key
        names must be detected.
        """
        resp = monitor.cmd_obj({"execute": "eject", "foobar": True})
        check_error_resp(
            resp, "GenericError", "QMP input member 'foobar' is unexpected"
        )

    def test_bad_arguments_key_type(monitor):
        """
        The "arguments" key must be an json-object.

        We use the eject command to perform the tests, but that's a random
        choice, any command that accepts arguments will do, as the command
        doesn't get called.
        """
        for item in (True, [], 1, "foo"):
            resp = monitor.cmd_obj({"execute": "eject", "arguments": item})
            check_error_resp(
                resp, "GenericError", "QMP input member 'arguments' must be an object"
            )

    def test_bad_execute_key_type(monitor):
        """
        The "execute" key must be a json-string.
        """
        for item in (False, 1, {}, []):
            resp = monitor.cmd_obj({"execute": item})
            check_error_resp(
                resp, "GenericError", "QMP input member 'execute' must be a string"
            )

    def test_no_execute_key(monitor):
        """
        The "execute" key must exist, we also test for some stupid parsing
        errors.
        """
        for cmd in (
            {},
            {"execut": "qmp_capabilities"},
            {"executee": "qmp_capabilities"},
            {"foo": "bar"},
        ):
            resp = monitor.cmd_obj(cmd)
            check_error_resp(resp)  # XXX: check class and data dict?

    def test_bad_input_obj_type(monitor):
        """
        The input object must be... an json-object.
        """
        for cmd in ("foo", [], True, 1):
            resp = monitor.cmd_obj(cmd)
            check_error_resp(resp, "GenericError", "QMP input must be a JSON object")

    def test_good_input_obj(monitor):
        """
        Basic success tests for issuing QMP commands.
        """
        # NOTE: We don't use the cmd_qmp() method here because the command
        # object is in a 'random' order
        resp = monitor.cmd_obj({"execute": "query-version"})
        check_success_resp(resp)

        resp = monitor.cmd_obj({"arguments": {}, "execute": "query-version"})
        check_success_resp(resp)

        idd = "1234foo"
        resp = monitor.cmd_obj({"id": idd, "execute": "query-version", "arguments": {}})
        check_success_resp(resp)
        check_str_key(resp, "id", idd)

        # TODO: would be good to test simple argument usage, but we don't have
        # a read-only command that accepts arguments.

    def input_object_suite(monitor):
        """
        Check the input object format, as described in the QMP specfication
        section '2.3 Issuing Commands'.

        { "execute": json-string, "arguments": json-object, "id": json-value }
        """
        test_good_input_obj(monitor)
        test_bad_input_obj_type(monitor)
        test_no_execute_key(monitor)
        test_bad_execute_key_type(monitor)
        test_bad_arguments_key_type(monitor)
        test_id_key(monitor)
        test_invalid_arg_key(monitor)

    def argument_checker_suite(monitor):
        """
        Check that QMP's argument checker is detecting all possible errors.

        We use a number of different commands to perform the checks, but the
        command used doesn't matter much as QMP performs argument checking
        _before_ calling the command.
        """
        # stop doesn't take arguments
        resp = monitor.cmd_qmp("stop", {"foo": 1})
        check_error_resp(resp, "GenericError", "Parameter 'foo' is unexpected")

        # required argument omitted
        resp = monitor.cmd_qmp("screendump")
        check_error_resp(resp, "GenericError", "Parameter 'filename' is missing")

        # 'bar' is not a valid argument
        resp = monitor.cmd_qmp("screendump", {"filename": "outfile", "bar": "bar"})
        check_error_resp(resp, "GenericError", "Parameter 'bar' is unexpected")

        # test optional argument: 'force' is omitted, but it's optional, so
        # the handler has to be called. Test this happens by checking an
        # error that is generated by the handler itself.
        resp = monitor.cmd_qmp("eject", {"device": "foobar"})
        check_error_resp(resp, "DeviceNotFound")

        # filename argument must be a json-string
        for arg in ({}, [], 1, True):
            resp = monitor.cmd_qmp("screendump", {"filename": arg})
            check_error_resp(
                resp,
                "GenericError",
                "Invalid parameter type for 'filename', expected: string",
            )

        # force argument must be a json-bool
        for arg in ({}, [], 1, "foo"):
            resp = monitor.cmd_qmp("eject", {"force": arg, "device": "foo"})
            check_error_resp(
                resp,
                "GenericError",
                "Invalid parameter type for 'force', expected: boolean",
            )

        # val argument must be a json-int
        for arg in ({}, [], True, "foo"):
            resp = monitor.cmd_qmp(
                "memsave", {"val": arg, "filename": "foo", "size": 10}
            )
            if utils_misc.compare_qemu_version(9, 1, 0, is_rhev=False) is True:
                check_error_resp(
                    resp,
                    "GenericError",
                    "Parameter 'val' expects uint64",
                )
            else:
                check_error_resp(
                    resp,
                    "GenericError",
                    "Invalid parameter type for 'val', expected: integer",
                )

        # value argument must be a json-number
        for arg in ({}, [], True, "foo"):
            if utils_misc.compare_qemu_version(5, 1, 0, is_rhev=False) is True:
                resp = monitor.cmd_qmp(
                    "migrate-set-parameters", {"downtime-limit": arg}
                )
                check_error_resp(
                    resp, "GenericError", "Parameter 'downtime-limit' expects uint64"
                )
            else:
                resp = monitor.cmd_qmp("migrate_set_downtime", {"value": arg})
                check_error_resp(
                    resp,
                    "GenericError",
                    "Invalid parameter type for 'value', expected: number",
                )

        # qdev-type commands have their own argument checker, all QMP does
        # is to skip its checking and pass arguments through. Check this
        # works by providing invalid options to device_add and expecting
        # an error message from qdev
        resp = monitor.cmd_qmp("device_add", {"driver": "e1000", "foo": "bar"})
        if params["machine_type"] == "q35":
            check_error_resp(
                resp, "GenericError", "Bus 'pcie.0' does not support hotplugging"
            )
        else:
            check_error_resp(resp, "GenericError", "Property 'e1000.foo' not found")

    def unknown_commands_suite(monitor):
        """
        Check that QMP handles unknown commands correctly.
        """
        # We also call a HMP-only command, to be sure it will fail as expected
        for cmd in ("bar", "query-", "query-foo", "q", "help"):
            resp = monitor.cmd_qmp(cmd)
            check_error_resp(
                resp, "CommandNotFound", "The command %s has not been found" % (cmd)
            )

    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()

    # Look for the first qmp monitor available, otherwise, fail the test
    qmp_monitor = vm.get_monitors_by_type("qmp")
    if qmp_monitor:
        qmp_monitor = qmp_monitor[0]
    else:
        test.error("Could not find a QMP monitor, aborting test")

    # Run all suites
    greeting_suite(qmp_monitor)
    input_object_suite(qmp_monitor)
    argument_checker_suite(qmp_monitor)
    unknown_commands_suite(qmp_monitor)
    json_parsing_errors_suite(qmp_monitor)

    # check if QMP is still alive
    if not qmp_monitor.is_responsive():
        test.fail("QMP monitor is not responsive after testing")
