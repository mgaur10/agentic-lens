"""
Vertex AI Search Data Store Setup Script
Creates a Data Store for the Events Department to search Google Cloud Events website.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

try:
    from google.cloud import discoveryengine
    from google.api_core import exceptions
except ImportError:
    print("❌ google-cloud-discoveryengine not installed.")
    print("   Install with: pip install google-cloud-discoveryengine")
    sys.exit(1)

try:
    from google.cloud import serviceusage
    SERVICE_USAGE_AVAILABLE = True
except ImportError:
    SERVICE_USAGE_AVAILABLE = False


def setup_data_store():
    """Create Vertex AI Search Data Store and Target Site."""
    
    # Get configuration from environment
    project_id = os.getenv("GCP_PROJECT_ID")
    # Discovery Engine uses "global" as the location, not regional locations
    location = "global"
    
    if not project_id:
        print("❌ GCP_PROJECT_ID not found in .env file.")
        print("   Please set GCP_PROJECT_ID in your .env file first.")
        sys.exit(1)
    
    print("=" * 60)
    print("🔍 Vertex AI Search Data Store Setup")
    print("=" * 60)
    print()
    print(f"📋 Project ID: {project_id}")
    print(f"📍 Location: {location}")
    print()
    
    # Set the project ID as an environment variable so Discovery Engine client uses it
    # This overrides the gcloud default project
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    
    # Also check and set gcloud config project if it's different
    import subprocess
    try:
        gcloud_project = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=5
        ).stdout.strip()
        
        if gcloud_project and gcloud_project != project_id:
            print(f"   ⚠️  gcloud default project is '{gcloud_project}', but using '{project_id}' from .env")
            print(f"   💡 Setting gcloud project to '{project_id}' for this session...")
            result = subprocess.run(
                ["gcloud", "config", "set", "project", project_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"   ✅ gcloud project set to '{project_id}'")
            else:
                print(f"   ⚠️  Could not set gcloud project: {result.stderr}")
        else:
            print(f"   ✅ gcloud project matches: {project_id}")
    except Exception as e:
        print(f"   ⚠️  Could not check/set gcloud project: {e}")
        print(f"   ℹ️  Using GOOGLE_CLOUD_PROJECT={project_id} environment variable")
    
    # Check Application Default Credentials project
    print()
    print("   🔍 Checking Application Default Credentials...")
    try:
        from google.auth import default as google_auth_default
        credentials, adc_project = google_auth_default()
        
        # The adc_project might be None, but credentials might have project_id
        cred_project = None
        if hasattr(credentials, 'project_id'):
            cred_project = credentials.project_id
        elif adc_project:
            cred_project = adc_project
        
        if cred_project and cred_project != project_id:
            print(f"   ⚠️  Application Default Credentials are for project '{cred_project}'")
            print(f"   ⚠️  This may cause API calls to use the wrong project!")
            print()
            print(f"   💡 To fix this, re-authenticate with the correct project:")
            print(f"      gcloud auth application-default login --project={project_id}")
            print()
            print(f"   ⚠️  Continuing anyway, but you may see project mismatch errors...")
        else:
            print(f"   ✅ Application Default Credentials project matches: {project_id}")
    except Exception as e:
        print(f"   ⚠️  Could not check Application Default Credentials: {e}")
    print()
    
    # Check if Discovery Engine API is enabled and enable it if needed
    print("🔍 Checking if Discovery Engine API is enabled...")
    print(f"   Using project: {project_id} (from .env file)")
    api_enabled = False
    
    try:
        # Try using Service Usage API to check and enable
        if SERVICE_USAGE_AVAILABLE:
            # Set project for Service Usage client
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            service_usage_client = serviceusage.ServiceUsageClient()
            service_name = f"projects/{project_id}/services/discoveryengine.googleapis.com"
            print(f"   Checking service: {service_name}")
            
            try:
                service = service_usage_client.get_service(name=service_name)
                if service.state == serviceusage.Service.State.ENABLED:
                    print("   ✅ Discovery Engine API is enabled.")
                    api_enabled = True
                else:
                    print("   ⚠️  Discovery Engine API is not enabled.")
                    print("   Enabling Discovery Engine API...")
                    operation = service_usage_client.enable_service(name=service_name)
                    operation.result(timeout=120)  # Wait up to 2 minutes
                    print("   ✅ Discovery Engine API enabled.")
                    api_enabled = True
            except exceptions.NotFound:
                print("   ⚠️  Discovery Engine API not found. Enabling...")
                operation = service_usage_client.enable_service(name=service_name)
                operation.result(timeout=120)
                print("   ✅ Discovery Engine API enabled.")
                api_enabled = True
            except Exception as e:
                print(f"   ⚠️  Could not enable API via Service Usage API: {e}")
        
        # Fallback: Try gcloud command if Service Usage API didn't work
        if not api_enabled:
            try:
                import subprocess
                import shutil
                
                # Check if gcloud is available
                gcloud_path = shutil.which("gcloud")
                if gcloud_path:
                    result = subprocess.run(
                        [gcloud_path, "services", "list", "--enabled", "--project", project_id, "--filter", "name:discoveryengine.googleapis.com"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if "discoveryengine.googleapis.com" in result.stdout:
                        print("   ✅ Discovery Engine API is enabled.")
                        api_enabled = True
                    else:
                        print("   ⚠️  Discovery Engine API not enabled.")
                        print("   Enabling Discovery Engine API via gcloud...")
                        subprocess.run(
                            [gcloud_path, "services", "enable", "discoveryengine.googleapis.com", "--project", project_id],
                            check=True,
                            timeout=120
                        )
                        print("   ✅ Discovery Engine API enabled.")
                        api_enabled = True
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                print(f"   ⚠️  Could not enable API via gcloud: {e}")
    except Exception as e:
        print(f"   ⚠️  Error checking/enabling API: {e}")
    
    if not api_enabled:
        print()
        print("   ⚠️  WARNING: Could not automatically enable Discovery Engine API.")
        print("   Please enable it manually:")
        print(f"   https://console.cloud.google.com/apis/library/discoveryengine.googleapis.com?project={project_id}")
        print()
        print("   Or run this command:")
        print(f"   gcloud services enable discoveryengine.googleapis.com --project={project_id}")
        print()
        print("   After enabling, wait 1-2 minutes for the API to propagate, then run this script again.")
        sys.exit(1)
    
    # Wait a bit for API to fully propagate
    # Wait a bit for API to fully propagate after enabling
    if api_enabled:
        print("   ⏳ Waiting 30 seconds for API to fully propagate...")
        import time
        time.sleep(30)
    print()
    
    # Initialize clients with global endpoint
    # Discovery Engine API requires the global endpoint, not regional endpoints
    try:
        from google.api_core import client_options as client_options_lib
        
        # Use global endpoint for Discovery Engine
        client_options = client_options_lib.ClientOptions(
            api_endpoint="discoveryengine.googleapis.com"  # Global endpoint (no region prefix)
        )
        
        data_store_client = discoveryengine.DataStoreServiceClient(client_options=client_options)
        site_search_client = discoveryengine.SiteSearchEngineServiceClient(client_options=client_options)
        
        # Verify we're using the correct project
        print(f"   ✅ Initialized clients with global endpoint")
        print(f"   📋 Will use project from resource paths: {project_id}")
    except Exception as e:
        print(f"❌ Failed to initialize Discovery Engine clients: {e}")
        print(f"   💡 If you see project mismatch errors, try:")
        print(f"      gcloud auth application-default login --project={project_id}")
        sys.exit(1)
    
    # Data Store configuration
    data_store_id = "events-web-knowledge"
    
    # For Discovery Engine, the collection path format is:
    # projects/{project}/locations/{location}/collections/default_collection
    collection_id = "default_collection"
    parent = f"projects/{project_id}/locations/{location}/collections/{collection_id}"
    data_store_name = f"{parent}/dataStores/{data_store_id}"
    
    print(f"   📍 Collection path: {parent}")
    print(f"   📍 Data Store path: {data_store_name}")
    
    # Step 0.5: Verify collection exists (Discovery Engine creates it automatically, but let's check)
    print("🔍 Step 0.5: Verifying collection exists...")
    try:
        # Try to list data stores in the collection to verify it exists
        # If collection doesn't exist, this will fail with 404
        list_request = discoveryengine.ListDataStoresRequest(parent=parent)
        list(data_store_client.list_data_stores(request=list_request))
        print("   ✅ Collection exists and is accessible.")
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            print("   ⚠️  Collection might not exist yet (will be created automatically with first data store).")
        else:
            print(f"   ⚠️  Could not verify collection: {e}")
    print()
    
    # Step 1: Check if Data Store exists
    print("🔍 Step 1: Checking if Data Store exists...")
    data_store_exists = False
    
    try:
        data_store = data_store_client.get_data_store(name=data_store_name)
        print(f"   ✅ Data Store already exists: {data_store.display_name}")
        data_store_exists = True
    except exceptions.NotFound:
        print("   ℹ️  Data Store does not exist. Will create it.")
        data_store_exists = False
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "NotFound" in error_str or "not found" in error_str.lower():
            print("   ℹ️  Data Store does not exist (404). Will create it.")
            data_store_exists = False
        else:
            print(f"   ⚠️  Error checking Data Store: {e}")
            print("   Will attempt to create it anyway.")
            data_store_exists = False
    
    # Step 2: Create Data Store if it doesn't exist
    if not data_store_exists:
        print()
        print("🔨 Step 2: Creating Data Store...")
        
        data_store_config = discoveryengine.DataStore(
            display_name="Events-Web-Knowledge",
            industry_vertical=discoveryengine.IndustryVertical.GENERIC,
            solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
            content_config=discoveryengine.DataStore.ContentConfig.PUBLIC_WEBSITE,
        )
        
        try:
            print(f"   📝 Creating Data Store with parent: {parent}")
            operation = data_store_client.create_data_store(
                parent=parent,
                data_store=data_store_config,
                data_store_id=data_store_id,
            )
            
            # Wait for operation to complete
            print("   ⏳ Waiting for Data Store creation to complete...")
            response = operation.result(timeout=300)  # 5 minute timeout
            
            print(f"   ✅ Data Store created successfully!")
            print(f"   📝 Display Name: {response.display_name}")
        except exceptions.AlreadyExists:
            print("   ✅ Data Store already exists (caught AlreadyExists exception).")
        except Exception as e:
            error_str = str(e)
            if "404" in error_str:
                print(f"   ❌ Failed to create Data Store: Collection or parent path not found (404)")
                print()
                print(f"   💡 Possible solutions:")
                print(f"   1. Wait 2-3 more minutes for the Discovery Engine API to fully propagate")
                print(f"   2. Create the Data Store manually in the Console:")
                print(f"      https://console.cloud.google.com/gen-app-builder/data-stores?project={project_id}")
                print()
                print(f"   3. The collection '{collection_id}' will be created automatically when you create")
                print(f"      the first data store. If this error persists, try creating it via Console.")
                print()
                print(f"   📋 Manual creation steps:")
                print(f"      - Go to: https://console.cloud.google.com/gen-app-builder/data-stores")
                print(f"      - Click 'Create Data Store'")
                print(f"      - Select 'Website' as the data source")
                print(f"      - Name: Events-Web-Knowledge")
                print(f"      - Add target site: https://www.googlecloudevents.com/next-vegas/*")
            elif "403" in error_str and ("SERVICE_DISABLED" in error_str or "has not been used" in error_str):
                # Check if it's a project mismatch error
                if project_id.lower() not in error_str.lower():
                    print(f"   ❌ Failed to create Data Store: Project mismatch error (403)")
                    print()
                    print(f"   ⚠️  The API is trying to use a different project than '{project_id}'")
                    print(f"   💡 This is likely because Application Default Credentials are for a different project.")
                    print()
                    print(f"   🔧 To fix this, re-authenticate with the correct project:")
                    print(f"      gcloud auth application-default login --project={project_id}")
                    print()
                    print(f"   Then run this script again.")
                else:
                    print(f"   ❌ Failed to create Data Store: API not enabled or not ready (403)")
                    print()
                    print(f"   💡 The Discovery Engine API might need more time to propagate.")
                    print(f"   💡 Wait 2-3 minutes and try again, or create manually in the Console:")
                    print(f"      https://console.cloud.google.com/gen-app-builder/data-stores?project={project_id}")
            else:
                print(f"   ❌ Failed to create Data Store: {e}")
            sys.exit(1)
    
    # Step 3: Create Target Site
    print()
    print("🌐 Step 3: Setting up Target Site...")
    
    target_site_uri = "https://www.googlecloudevents.com/next-vegas"
    target_site_pattern = "https://www.googlecloudevents.com/next-vegas/*"
    
    # Get the site search engine name
    site_search_engine_name = f"{data_store_name}/siteSearchEngine"
    
    try:
        # Check if target site already exists
        target_sites = site_search_client.list_target_sites(parent=site_search_engine_name)
        existing_sites = list(target_sites)
        
        site_exists = False
        for site in existing_sites:
            if site.provided_uri_pattern == target_site_pattern or site.exact_match == True:
                print(f"   ✅ Target Site already exists: {site.provided_uri_pattern}")
                site_exists = True
                break
        
        if not site_exists:
            # Create target site
            target_site = discoveryengine.TargetSite(
                provided_uri_pattern=target_site_pattern,
                exact_match=True,
                type_=discoveryengine.TargetSite.Type.INCLUDE,
            )
            
            operation = site_search_client.create_target_site(
                parent=site_search_engine_name,
                target_site=target_site,
            )
            
            print("   ⏳ Waiting for Target Site creation to complete...")
            response = operation.result(timeout=300)  # 5 minute timeout
            
            print(f"   ✅ Target Site created successfully!")
            print(f"   📝 Pattern: {response.provided_uri_pattern}")
        else:
            print("   ℹ️  Target Site already configured.")
            
    except Exception as e:
        print(f"   ⚠️  Warning: Could not configure Target Site: {e}")
        print("   You may need to configure it manually in the Console.")
        print(f"   Site Search Engine: {site_search_engine_name}")
    
    # Step 4: Output the Data Store ID
    print()
    print("=" * 60)
    print("✅ Setup Complete!")
    print("=" * 60)
    print()
    print("\033[1;32m" + "📋 DATA_STORE_ID (copy this to your .env file):" + "\033[0m")
    print("\033[1;32m" + f"   {data_store_id}" + "\033[0m")
    print()
    print("📝 Add this to your .env file:")
    print(f"   VERTEX_SEARCH_DATA_STORE_ID={data_store_id}")
    print()
    print("💡 Next Steps:")
    print("   1. Copy the DATA_STORE_ID above")
    print("   2. Add it to your .env file as VERTEX_SEARCH_DATA_STORE_ID")
    print("   3. The Events Agent will use this Data Store for grounding")
    print()


if __name__ == "__main__":
    setup_data_store()
