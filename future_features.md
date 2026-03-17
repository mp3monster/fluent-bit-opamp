# ToDos and Future Features
The following represents a brain dump of things that we want to/need to do.  The ToDos are the primary focus - but may not be delivered immediately as we work to providing a minimal implementation.

## ToDos

### Client Side
* Ensure uid is compliant with uuid v7 spec
* Provide a compliant uid if one its defined and update configuration
* set header correctly based on channel
* add validation and hardwire heartbeat feature
* validate ServerToAgent payload against feature capabilities


### Server Side
* validate uid


## Future Features

### All
* GitHub driven test rig

### Client Side
* Allow consumer attributes to come from commenting block in Fluent Bit configuration
* extend so configuration can be classic
* Certificate management - this is messy to setup and test properly
* code signing
* wheel package
* configure drive overloading of operations - so process checks can have alternate implementations

### server Side
* Add authentication framework for the UI and APIs - currently we operate in a Jaeger style trust arrangement
* Implement persistence mechanism
* UI so that specific nodes and global polling can be set
* send configurations to multiple nodes at once
* Certificate management - this is messy to setup and test properly
* code signing
* wheel package
  