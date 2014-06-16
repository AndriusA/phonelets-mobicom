/*
 *  oFono - Open Source Telephony
 *
 *  Copyright (C) 2013  Instituto Nokia de Tecnologia - INdT
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License version 2 as
 *  published by the Free Software Foundation.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 *
 */

#ifdef HAVE_CONFIG_H
#include <config.h>
#endif

#include <stdint.h>
#include <sys/socket.h>
#include <gdbus.h>
#include <errno.h>

#include "dundee.h"
#include "plugins/bluez5.h"

#define DUN_DT_PROFILE_PATH   "/bluetooth/profile/dun_dt"

static GDBusClient *bluez;
static GHashTable *registered_devices;

struct bluetooth_device {
	struct dundee_device *device;

	char *path;
	char *address;
	char *name;

	struct cb_data *connect_cbd;

	int fd;
};

static DBusMessage *profile_new_connection(DBusConnection *conn,
					DBusMessage *msg, void *user_data)
{
	struct bluetooth_device *bt_device;
	dundee_device_connect_cb_t cb;
	DBusMessageIter iter;
	const char *path;
	int fd;

	if (!dbus_message_iter_init(msg, &iter))
		goto error;

	if (dbus_message_iter_get_arg_type(&iter) != DBUS_TYPE_OBJECT_PATH)
		goto error;

	dbus_message_iter_get_basic(&iter, &path);

	bt_device = g_hash_table_lookup(registered_devices, path);
	if (bt_device == NULL)
		goto error;

	cb = bt_device->connect_cbd->cb;

	dbus_message_iter_next(&iter);
	if (dbus_message_iter_get_arg_type(&iter) != DBUS_TYPE_UNIX_FD)
		goto call_failure;

	dbus_message_iter_get_basic(&iter, &fd);
	if (fd < 0)
		goto call_failure;

	DBG("%s %d", bt_device->path, fd);

	bt_device->fd = fd;

	CALLBACK_WITH_SUCCESS(cb, fd, bt_device->connect_cbd->data);

	g_free(bt_device->connect_cbd);
	bt_device->connect_cbd = NULL;

	return dbus_message_new_method_return(msg);

call_failure:
	CALLBACK_WITH_FAILURE(cb, -1, bt_device->connect_cbd->data);

	g_free(bt_device->connect_cbd);
	bt_device->connect_cbd = NULL;

error:
	return g_dbus_create_error(msg, BLUEZ_ERROR_INTERFACE ".Rejected",
					"Invalid arguments in method call");
}

static DBusMessage *profile_release(DBusConnection *conn,
					DBusMessage *msg, void *user_data)
{
	DBG("");

	return g_dbus_create_error(msg, BLUEZ_ERROR_INTERFACE
						".NotImplemented",
						"Implementation not provided");
}

static DBusMessage *profile_cancel(DBusConnection *conn,
					DBusMessage *msg, void *user_data)
{
	DBG("");

	return g_dbus_create_error(msg, BLUEZ_ERROR_INTERFACE
						".NotImplemented",
						"Implementation not provided");
}

static DBusMessage *profile_disconnection(DBusConnection *conn,
					DBusMessage *msg, void *user_data)
{
	struct bluetooth_device *bt_device;
	DBusMessageIter iter;
	const char *path;

	if (!dbus_message_iter_init(msg, &iter))
		goto error;

	if (dbus_message_iter_get_arg_type(&iter) != DBUS_TYPE_OBJECT_PATH)
		goto error;

	dbus_message_iter_get_basic(&iter, &path);

	bt_device = g_hash_table_lookup(registered_devices, path);
	if (bt_device == NULL)
		goto error;

	DBG("%s", bt_device->path);

	CALLBACK_WITH_SUCCESS(dundee_device_disconnect, bt_device->device);

	return dbus_message_new_method_return(msg);

error:
	return g_dbus_create_error(msg, BLUEZ_ERROR_INTERFACE ".Rejected",
					"Invalid arguments in method call");
}

static const GDBusMethodTable profile_methods[] = {
	{ GDBUS_ASYNC_METHOD("NewConnection",
				GDBUS_ARGS({ "device", "o"}, { "fd", "h"},
						{ "fd_properties", "a{sv}" }),
				NULL, profile_new_connection) },
	{ GDBUS_METHOD("Release", NULL, NULL, profile_release) },
	{ GDBUS_METHOD("Cancel", NULL, NULL, profile_cancel) },
	{ GDBUS_METHOD("RequestDisconnection",
				GDBUS_ARGS({"device", "o"}), NULL,
				profile_disconnection) },
	{ }
};

static void bluetooth_device_destroy(gpointer user_data)
{
	struct bluetooth_device *bt_device = user_data;

	DBG("%s", bt_device->path);

	if (bt_device->device != NULL)
		dundee_device_unregister(bt_device->device);

	if (bt_device->connect_cbd != NULL)
		g_free(bt_device->connect_cbd);

	g_free(bt_device->path);
	g_free(bt_device->address);
	g_free(bt_device->name);
	g_free(bt_device);
}

static void bluetooth_device_connect_callback(gboolean success,
							gpointer user_data)
{
	struct bluetooth_device *bt_device = user_data;

	if (success) {
		DBG("Success");
		return;
	}

	DBG("ConnectProfile() returned an error");

	g_free(bt_device->connect_cbd);
	bt_device->connect_cbd = NULL;
}

static void bluetooth_device_connect(struct dundee_device *device,
			dundee_device_connect_cb_t cb, void *data)
{
	struct bluetooth_device *bt_device = dundee_device_get_data(device);
	struct cb_data *cbd = cb_data_new(cb, data);

	DBG("%s", bt_device->path);

	cbd->user = bt_device;
	bt_device->connect_cbd = cbd;

	bt_connect_profile(ofono_dbus_get_connection(), bt_device->path,
		DUN_GW_UUID, bluetooth_device_connect_callback, bt_device);
}

static void bluetooth_device_disconnect(struct dundee_device *device,
				dundee_device_disconnect_cb_t cb, void *data)
{
	struct bluetooth_device *bt_device = dundee_device_get_data(device);

	DBG("%s", bt_device->path);

	shutdown(bt_device->fd, SHUT_RDWR);
	CALLBACK_WITH_SUCCESS(cb, data);
}

struct dundee_device_driver bluetooth_driver = {
	.name = "bluetooth",
	.connect = bluetooth_device_connect,
	.disconnect = bluetooth_device_disconnect,
};

static struct bluetooth_device *bluetooth_device_create(const char *path,
					const char *address, const char *alias)
{
	struct bluetooth_device *bt_device;

	DBG("%s %s %s", path, address, alias);

	bt_device = g_try_new0(struct bluetooth_device, 1);
	if (bt_device == NULL)
		return NULL;

	bt_device->path = g_strdup(path);
	bt_device->address = g_strdup(address);
	bt_device->name = g_strdup(alias);

	return bt_device;
}

static struct bluetooth_device *bluetooth_device_register(GDBusProxy *proxy)
{
	const char *path = g_dbus_proxy_get_path(proxy);
	const char *alias, *address;
	struct bluetooth_device *bt_device;
	struct dundee_device *device;
	DBusMessageIter iter;

	DBG("%s", path);

	if (g_hash_table_lookup(registered_devices, path) != NULL)
		return NULL;

	if (!g_dbus_proxy_get_property(proxy, "Address", &iter))
		return NULL;

	dbus_message_iter_get_basic(&iter, &address);

	if (!g_dbus_proxy_get_property(proxy, "Alias", &iter))
		return NULL;

	dbus_message_iter_get_basic(&iter, &alias);

	bt_device = bluetooth_device_create(path, address, alias);
	if (bt_device == NULL) {
		ofono_error("Register bluetooth device failed");
		return NULL;
	}

	device = dundee_device_create(&bluetooth_driver);
	if (device == NULL)
		goto free;

	dundee_device_set_data(device, bt_device);
	dundee_device_set_name(device, bt_device->name);

	if (dundee_device_register(device) < 0) {
		g_free(device);
		goto free;
	}

	bt_device->device = device;
	g_hash_table_insert(registered_devices, g_strdup(path), bt_device);

	return bt_device;

free:
	bluetooth_device_destroy(bt_device);
	return NULL;
}

static void bluetooth_device_unregister(const char *path)
{
	DBG("");

	g_hash_table_remove(registered_devices, path);
}

static gboolean has_dun_uuid(DBusMessageIter *array)
{
	DBusMessageIter value;

	if (dbus_message_iter_get_arg_type(array) != DBUS_TYPE_ARRAY)
		return FALSE;

	dbus_message_iter_recurse(array, &value);

	while (dbus_message_iter_get_arg_type(&value) == DBUS_TYPE_STRING) {
		const char *uuid;

		dbus_message_iter_get_basic(&value, &uuid);

		if (g_str_equal(uuid, DUN_GW_UUID))
			return TRUE;

		dbus_message_iter_next(&value);
	}

	return FALSE;
}

static void alias_changed(GDBusProxy *proxy, const char *name,
					DBusMessageIter *iter, void *user_data)
{
	const char *alias;
	struct bluetooth_device *bt_device = user_data;

	if (!g_str_equal("Alias", name))
		return;

	dbus_message_iter_get_basic(iter, &alias);

	bt_device->name = g_strdup(alias);
}

static void bluetooth_device_removed(GDBusProxy *proxy, void *user_data)
{
	struct bluetooth_device *bt_device = user_data;

	DBG("%s", bt_device->path);

	bluetooth_device_unregister(bt_device->path);
}

static void proxy_added(GDBusProxy *proxy, void *user_data)
{
	const char *path = g_dbus_proxy_get_path(proxy);
	const char *interface = g_dbus_proxy_get_interface(proxy);
	struct bluetooth_device *bt_device;
	DBusMessageIter iter;

	if (!g_str_equal(BLUEZ_DEVICE_INTERFACE, interface))
		return;

	if (!g_dbus_proxy_get_property(proxy, "UUIDs", &iter))
		return;

	DBG("%s %s", path, interface);

	if (!has_dun_uuid(&iter))
		return;

	bt_device = bluetooth_device_register(proxy);
	g_dbus_proxy_set_property_watch(proxy, alias_changed, bt_device);
	g_dbus_proxy_set_removed_watch(proxy, bluetooth_device_removed,
								bt_device);
}

static void connect_handler(DBusConnection *conn, void *user_data)
{
	DBG("");

	bt_register_profile(conn, DUN_GW_UUID, DUN_VERSION_1_2, "dun_dt",
					DUN_DT_PROFILE_PATH, "client", 0);
}

int __dundee_bluetooth_init(void)
{
	DBusConnection *conn = ofono_dbus_get_connection();

	DBG("");

	if (!g_dbus_register_interface(conn, DUN_DT_PROFILE_PATH,
					BLUEZ_PROFILE_INTERFACE,
					profile_methods, NULL,
					NULL, NULL, NULL)) {
		ofono_error("Register Profile interface failed: %s",
						DUN_DT_PROFILE_PATH);
		return -EIO;
	}

	bluez = g_dbus_client_new(conn, BLUEZ_SERVICE, BLUEZ_MANAGER_PATH);
	g_dbus_client_set_connect_watch(bluez, connect_handler, NULL);
	g_dbus_client_set_proxy_handlers(bluez, proxy_added, NULL, NULL, NULL);

	registered_devices = g_hash_table_new_full(g_str_hash, g_str_equal,
					g_free, bluetooth_device_destroy);

	return 0;
}

void __dundee_bluetooth_cleanup(void)
{
	DBusConnection *conn = ofono_dbus_get_connection();

	DBG("");

	g_dbus_unregister_interface(conn, DUN_DT_PROFILE_PATH,
						BLUEZ_PROFILE_INTERFACE);

	g_dbus_client_unref(bluez);
	g_hash_table_destroy(registered_devices);
}
