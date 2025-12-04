# MongoDB Atlas Connection Fix

## Issue Summary

**Date**: October 26, 2025  
**Service**: `petrosa-realtime-strategies`  
**Severity**: Critical - Service unable to persist configuration data

### Problem

The realtime-strategies service was attempting to connect to a non-existent local Kubernetes MongoDB service (`mongodb-service.petrosa-apps.svc.cluster.local:27017`) instead of MongoDB Atlas.

**Error Log**:
```
Failed to connect to MongoDB: mongodb-service.petrosa-apps.svc.cluster.local:27017: [Errno -2] Name does not resolve
```

## Root Cause

The service deployment was configured to use the wrong secret key for MongoDB connection:

**Incorrect Configuration** (`k8s/deployment.yaml` line 198):
```yaml
- name: MONGODB_URI
  valueFrom:
    secretKeyRef:
      name: petrosa-sensitive-credentials
      key: mongodb-url  # ❌ Points to local cluster service
```

The secret `petrosa-sensitive-credentials` contains two MongoDB connection strings:
- `mongodb-url`: `mongodb://mongodb-service.petrosa-apps.svc.cluster.local:27017` (local cluster - does not exist)
- `mongodb-connection-string`: `mongodb+srv://yurisa2:***@petrosa.gynnmi6.mongodb.net/` (MongoDB Atlas - correct)

## Solution

Updated the deployment to use the correct secret key:

**Correct Configuration** (`k8s/deployment.yaml` line 198):
```yaml
- name: MONGODB_URI
  valueFrom:
    secretKeyRef:
      name: petrosa-sensitive-credentials
      key: mongodb-connection-string  # ✅ Points to MongoDB Atlas
```

## Changes Made

### 1. Updated Deployment Configuration
- **File**: `/Users/yurisa2/petrosa/petrosa-realtime-strategies/k8s/deployment.yaml`
- **Line**: 198
- **Change**: Changed secret key from `mongodb-url` to `mongodb-connection-string`

### 2. Applied Configuration
```bash
kubectl --kubeconfig=k8s/kubeconfig.yaml apply -f k8s/deployment.yaml
kubectl --kubeconfig=k8s/kubeconfig.yaml set image deployment/petrosa-realtime-strategies realtime-strategies=yurisa2/petrosa-realtime-strategies:v1.0.36 -n petrosa-apps
kubectl --kubeconfig=k8s/kubeconfig.yaml rollout restart deployment/petrosa-realtime-strategies -n petrosa-apps
```

### 3. Verified Fix
All pods now successfully connect to MongoDB Atlas:
```
Using direct MongoDB connection
Configuration manager MongoDB connection established
```

Connection string now resolves to Atlas cluster:
- `ac-f8t02yd-shard-00-00.gynnmi6.mongodb.net`
- `ac-f8t02yd-shard-00-01.gynnmi6.mongodb.net`
- `ac-f8t02yd-shard-00-02.gynnmi6.mongodb.net`

## Current Status

✅ **All pods (3/3) running and healthy**  
✅ **MongoDB Atlas connection established**  
✅ **Configuration manager operational**  
✅ **NATS connections active**  
✅ **Messages processing normally**

## Verification Commands

Check pod status:
```bash
kubectl --kubeconfig=k8s/kubeconfig.yaml get pods -n petrosa-apps -l app=realtime-strategies
```

Check MongoDB connection logs:
```bash
kubectl --kubeconfig=k8s/kubeconfig.yaml logs -n petrosa-apps -l app=realtime-strategies | grep -i "mongo"
```

## Notes

- Temporary "timed out" or "No replica set members found yet" messages during pod startup are normal for MongoDB Atlas replica sets
- The connection successfully establishes within 5-10 seconds after pod startup
- This fix aligns with how other services (e.g., `petrosa-tradeengine`) connect to MongoDB Atlas

## Related Services

Other services should verify they're using the correct secret key:
- ✅ `petrosa-tradeengine` - Uses `mongodb-connection-string` (correct)
- ✅ `petrosa-realtime-strategies` - Now fixed to use `mongodb-connection-string`
- ⚠️ `petrosa-data-manager` - Should verify configuration
- ⚠️ `petrosa-binance-data-extractor` - Uses MySQL, not MongoDB

## Prevention

1. The master cursorrules should document the correct secret key to use for MongoDB Atlas
2. Consider deprecating/removing the `mongodb-url` secret key to prevent confusion
3. Add deployment validation to catch incorrect secret references

## References

- MongoDB Atlas Cluster: `petrosa.gynnmi6.mongodb.net`
- Secret Name: `petrosa-sensitive-credentials` (namespace: `petrosa-apps`)
- Correct Secret Key: `mongodb-connection-string`
- Service: `petrosa-realtime-strategies`
- Deployment: `petrosa-realtime-strategies` (namespace: `petrosa-apps`)

