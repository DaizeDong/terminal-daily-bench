# Load URDFs with a floating base, a reused name, or an unnamed actuator

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

A `floating` or `planar` joint had no branch, so the joint object was never built and the load raised `UnboundLocalError`; an unsupported type now attaches the child rigidly at the joint origin with a warning, which is the pose `Joint.get_child_pose` already returns for those two at zero configuration.

URDF keeps link and joint names in separate namespaces, so a joint sharing the base link's name overwrote that link in the model's attributes and `root_link` came back as a joint; it is now resolved among the links.

An `<actuator>` with no name aborted the parse even though nothing here reads that name, so the name is optional now.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
