"""Implementazione sensori di pun_sensor."""

from typing import Any

from awesomeversion.awesomeversion import AwesomeVersion

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PUNDataUpdateCoordinator
from .const import DOMAIN
from .interfaces import Fascia, PunValues

ATTR_ROUNDED_DECIMALS = "rounded_decimals"


class CommonSettings:
    """Contiene variabili globali a tutte le classi."""

    has_suggested_display_precision = False


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Inizializza e crea i sensori."""

    # Restituisce il coordinator
    coordinator = hass.data[DOMAIN][config.entry_id]

    # Verifica la versione di Home Assistant
    CommonSettings.has_suggested_display_precision = AwesomeVersion(
        HA_VERSION
    ) >= AwesomeVersion("2023.3.0")

    # Crea i sensori dei valori del pun (legati al coordinator)
    entities: list[SensorEntity] = []
    entities.extend(
        PUNSensorEntity(coordinator, fascia) for fascia in PunValues().value
    )

    # Crea sensori aggiuntivi
    entities.append(FasciaPUNSensorEntity(coordinator))
    entities.append(PrezzoFasciaPUNSensorEntity(coordinator))

    # Aggiunge i sensori ma non aggiorna automaticamente via web
    # per lasciare il tempo ad Home Assistant di avviarsi
    async_add_entities(entities, update_before_add=False)


def fmt_float(num: float) -> float:
    """Formatta adeguatamente il numero decimale."""
    if CommonSettings.has_suggested_display_precision:
        return num

    # In versioni precedenti di Home Assistant che non supportano
    # l'attributo 'suggested_display_precision' restituisce il numero
    # decimale già arrotondato
    return round(num, 6)


class PUNSensorEntity(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Sensore PUN relativo al prezzo medio mensile per fasce."""

    def __init__(self, coordinator: PUNDataUpdateCoordinator, fascia: Fascia) -> None:
        """Inizializza il sensore."""
        super().__init__(coordinator)

        # Inizializza coordinator e tipo
        self.coordinator = coordinator
        self.fascia = fascia

        # ID univoco sensore basato su un nome fisso
        match self.fascia:
            case Fascia.MONO:
                self.entity_id = ENTITY_ID_FORMAT.format("pun_mono_orario")
            case Fascia.F1:
                self.entity_id = ENTITY_ID_FORMAT.format("pun_fascia_f1")
            case Fascia.F2:
                self.entity_id = ENTITY_ID_FORMAT.format("pun_fascia_f2")
            case Fascia.F3:
                self.entity_id = ENTITY_ID_FORMAT.format("pun_fascia_f3")
            case Fascia.F23:
                self.entity_id = ENTITY_ID_FORMAT.format("pun_fascia_f23")
            case _:
                self.entity_id = None
        self._attr_unique_id = self.entity_id
        self._attr_has_entity_name = True

        # Inizializza le proprietà comuni
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 6
        self._available = False
        self._native_value = 0

    def _handle_coordinator_update(self) -> None:
        """Gestisce l'aggiornamento dei dati dal coordinator."""
        if self.fascia != Fascia.F23:
            # Tutte le fasce tranne F23
            if len(self.coordinator.pun_data.pun[self.fascia]) > 0:
                # Ci sono dati, sensore disponibile
                self._available = True
                self._native_value = self.coordinator.pun_values.value[self.fascia]
            else:
                # Non ci sono dati, sensore non disponibile
                self._available = False

        elif (
            len(self.coordinator.pun_data.pun[Fascia.F2])
            and len(self.coordinator.pun_data.pun[Fascia.F3])
        ) > 0:
            # Caso speciale per fascia F23: affinché sia disponibile devono
            # esserci dati sia sulla fascia F2 che sulla F3,
            # visto che è calcolata a partire da questi
            self._available = True
            self._native_value = self.coordinator.pun_values.value[self.fascia]
        else:
            # Non ci sono dati, sensore non disponibile
            self._available = False

        # Aggiorna lo stato di Home Assistant
        self.async_write_ha_state()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Determina i dati da salvare per il ripristino successivo."""
        return RestoredExtraData(
            {"native_value": self._native_value if self._available else None}
        )

    async def async_added_to_hass(self) -> None:
        """Entità aggiunta ad Home Assistant."""
        await super().async_added_to_hass()

        # Recupera lo stato precedente, se esiste
        if (old_data := await self.async_get_last_extra_data()) is not None:
            if (old_native_value := old_data.as_dict().get("native_value")) is not None:
                self._available = True
                self._native_value = old_native_value

    @property
    def should_poll(self) -> bool:
        """Determina l'aggiornamento automatico."""
        return False

    @property
    def available(self) -> bool:
        """Determina se il valore è disponibile."""
        return self._available

    @property
    def native_value(self) -> float:
        """Valore corrente del sensore."""
        return fmt_float(self._native_value)

    @property
    def native_unit_of_measurement(self) -> str:
        """Unita' di misura."""
        return f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"

    @property
    def icon(self) -> str:
        """Icona da usare nel frontend."""
        return "mdi:chart-line"

    @property
    def name(self) -> str | None:
        """Restituisce il nome del sensore."""
        if self.fascia == Fascia.MONO:
            return "PUN mono-orario"
        if self.fascia:
            return f"PUN fascia {self.fascia.value}"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Restituisce gli attributi di stato."""
        if CommonSettings.has_suggested_display_precision:
            return {}

        # Nelle versioni precedenti di Home Assistant
        # restituisce un valore arrotondato come attributo
        return {ATTR_ROUNDED_DECIMALS: str(format(round(self.native_value, 3), ".3f"))}


class FasciaPUNSensorEntity(CoordinatorEntity, SensorEntity):
    """Sensore che rappresenta il nome la fascia oraria PUN corrente."""

    def __init__(self, coordinator: PUNDataUpdateCoordinator) -> None:
        """Inizializza il sensore."""
        super().__init__(coordinator)

        # Inizializza coordinator
        self.coordinator = coordinator

        # ID univoco sensore basato su un nome fisso
        self.entity_id = ENTITY_ID_FORMAT.format("pun_fascia_corrente")
        self._attr_unique_id = self.entity_id
        self._attr_has_entity_name = True

    def _handle_coordinator_update(self) -> None:
        """Gestisce l'aggiornamento dei dati dal coordinator."""
        self.async_write_ha_state()

    @property
    def should_poll(self) -> bool:
        """Determina l'aggiornamento automatico."""
        return False

    @property
    def available(self) -> bool:
        """Determina se il valore è disponibile."""
        return self.coordinator.fascia_corrente is not None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Classe del sensore."""
        return SensorDeviceClass.ENUM

    @property
    def options(self) -> list[str] | None:
        """Possibili stati del sensore."""
        return [Fascia.F1.value, Fascia.F2.value, Fascia.F3.value]

    @property
    def native_value(self) -> str | None:
        """Restituisce la fascia corrente come stato."""
        if not self.coordinator.fascia_corrente:
            return None
        return self.coordinator.fascia_corrente.value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributi aggiuntivi del sensore."""
        return {
            "fascia_successiva": self.coordinator.fascia_successiva.value
            if self.coordinator.fascia_successiva
            else None,
            "inizio_fascia_successiva": self.coordinator.prossimo_cambio_fascia,
            "termine_fascia_successiva": self.coordinator.termine_prossima_fascia,
        }

    @property
    def icon(self) -> str:
        """Icona da usare nel frontend."""
        return "mdi:timeline-clock-outline"

    @property
    def name(self) -> str:
        """Restituisce il nome del sensore."""
        return "Fascia corrente"


class PrezzoFasciaPUNSensorEntity(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Sensore che rappresenta il prezzo PUN della fascia corrente."""

    def __init__(self, coordinator: PUNDataUpdateCoordinator) -> None:
        """Inizializza il sensore."""
        super().__init__(coordinator)

        # Inizializza coordinator
        self.coordinator = coordinator

        # ID univoco sensore basato su un nome fisso
        self.entity_id = ENTITY_ID_FORMAT.format("pun_prezzo_fascia_corrente")
        self._attr_unique_id = self.entity_id
        self._attr_has_entity_name = True

        # Inizializza le proprietà comuni
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 6
        self._available = False
        self._native_value = 0
        self._friendly_name = "Prezzo fascia corrente"

    def _handle_coordinator_update(self) -> None:
        """Gestisce l'aggiornamento dei dati dal coordinator."""
        if self.coordinator.fascia_corrente is not None:
            self._available = (
                len(self.coordinator.pun_data.pun[self.coordinator.fascia_corrente]) > 0
            )
            self._native_value = self.coordinator.pun_values.value[
                self.coordinator.fascia_corrente
            ]
            self._friendly_name = (
                f"Prezzo fascia corrente ({self.coordinator.fascia_corrente.value})"
            )
        else:
            self._available = False
            self._native_value = 0
            self._friendly_name = "Prezzo fascia corrente"
        self.async_write_ha_state()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Determina i dati da salvare per il ripristino successivo."""
        return RestoredExtraData(
            {
                "native_value": self._native_value if self._available else None,
                "friendly_name": self._friendly_name if self._available else None,
            }
        )

    async def async_added_to_hass(self) -> None:
        """Entità aggiunta ad Home Assistant."""
        await super().async_added_to_hass()

        # Recupera lo stato precedente, se esiste
        if (old_data := await self.async_get_last_extra_data()) is not None:
            if (old_native_value := old_data.as_dict().get("native_value")) is not None:
                self._available = True
                self._native_value = old_native_value
            if (
                old_friendly_name := old_data.as_dict().get("friendly_name")
            ) is not None:
                self._friendly_name = old_friendly_name

    @property
    def should_poll(self) -> bool:
        """Determina l'aggiornamento automatico."""
        return False

    @property
    def available(self) -> bool:
        """Determina se il valore è disponibile."""
        return self._available

    @property
    def native_value(self) -> float:
        """Restituisce il prezzo della fascia corrente."""
        return fmt_float(self._native_value)

    @property
    def native_unit_of_measurement(self) -> str:
        """Unita' di misura."""
        return f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"

    @property
    def icon(self) -> str:
        """Icona da usare nel frontend."""
        return "mdi:currency-eur"

    @property
    def name(self) -> str:
        """Restituisce il nome del sensore."""
        return self._friendly_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Restituisce gli attributi di stato."""
        if CommonSettings.has_suggested_display_precision:
            return {}

        # Nelle versioni precedenti di Home Assistant
        # restituisce un valore arrotondato come attributo
        return {ATTR_ROUNDED_DECIMALS: str(format(round(self.native_value, 3), ".3f"))}
