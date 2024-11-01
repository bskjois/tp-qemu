import os

from virttest import error_context as error
from virttest import utils_misc, utils_net, utils_test


@error.context_aware
def run(test, params, env):
    """
    Test nic driver in promisc mode:

    1) Boot up a VM.
    2) Repeatedly enable/disable promiscuous mode in guest.
    3) Transfer file between host and guest during nic promisc on/off

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    """

    def set_nic_promisc_onoff(session):
        if os_type == "linux":
            session.cmd_output_safe("ip link set %s promisc on" % ethname)
            session.cmd_output_safe("ip link set %s promisc off" % ethname)
        else:
            cmd = "c:\\set_win_promisc.py"
            session.cmd(cmd)

    error.context("Boot vm and prepare test environment", test.log.info)
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = int(params.get("login_timeout", 360))
    session_serial = vm.wait_for_serial_login(timeout=timeout)
    session = vm.wait_for_login(timeout=timeout)

    os_type = params.get("os_type")
    if os_type == "linux":
        ethname = utils_net.get_linux_ifname(session, vm.get_mac_address(0))
    else:
        script_path = os.path.join(test.virtdir, "scripts/set_win_promisc.py")
        vm.copy_files_to(script_path, "C:\\")

    try:
        transfer_thread = utils_misc.InterruptedThread(
            utils_test.run_file_transfer, (test, params, env)
        )

        error.context("Run utils_test.file_transfer ...", test.log.info)
        transfer_thread.start()

        error.context(
            "Perform file transfer while turning nic promisc on/off", test.log.info
        )
        while transfer_thread.is_alive():
            set_nic_promisc_onoff(session_serial)
    except Exception:
        transfer_thread.join(suppress_exception=True)
        raise
    else:
        transfer_thread.join()
        if session:
            session.close()
