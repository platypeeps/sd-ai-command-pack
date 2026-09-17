"""What is left of the pack's own dashboard: the package marker, and nothing else.

The views this package served -- the fleet, the tracker index, the Now
ranking, the action runner and the `deliver` write -- moved to the system
dashboard one sd:719 step at a time, and the modules went with them; step 6
took the last five. The one write, `deliver`, is `sd work deliver` now. This
file stays so the tree under `dashboard/` is a package until step 7 deletes
the directory, `bin/sd-dashboard` and the ceilings on it in one commit.
"""
